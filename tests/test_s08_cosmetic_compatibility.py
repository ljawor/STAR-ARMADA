"""S08 headless cosmetic compatibility evidence, not historical-user-file claims.

Run with PYTHONPATH=tests:. <venv-python> -m unittest
    test_s08_cosmetic_compatibility -v
Optional S08_COSMETIC_EVIDENCE names a disposable evidence output directory.
All persistence and peer traces otherwise live in TemporaryDirectory under scratch.

The legacy fixture is deliberately generated from the current production codec,
then loses runtime_state BEFORE historical projection fields. It exercises the
supported missing sensor/crew/collection/upgrade defaults, not a recovered old
user save. Fresh brains/reset timers cannot reproduce unrecorded historical AI.
The equality claim is between identical migrated inputs under different visuals.
Legacy v1 playback cannot validate original content or unknown commandless tails.
"""
import copy
import gzip
import hashlib
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import tempfile
import time
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
SCRATCH = ROOT.parent
STEPS = 180
DT = 1 / 30
HISTORICAL_FIELDS = ('sensor_range', 'collection_point', 'upgrade_level',
                     'crew', 'max_crew', 'crew_loss_accumulator',
                     'crew_damage_accumulator', 'crew_cargo', 'crew_mission',
                     'cargo_loss_accumulator', 'boarding', 'boarding_party_id',
                     'recruitment_progress', 'abandoned_attack_target')


def dump(path, value):
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text(json.dumps(value, sort_keys=True, indent=2), encoding='utf-8')


def load(path):
    return json.loads(Path(path).read_text(encoding='utf-8'))


def normalized(value):
    return json.loads(json.dumps(value, allow_nan=False))


def make_packs(folder):
    """Two real derived 7,708-triangle frigates, never the one-triangle test stub.

    Uniform scale preserves authored normals; both shrink within the approved
    binding envelope. These test derivatives expressly do not claim owner approval.
    """
    for name, scale in [('amber', .96), ('blue', .92)]:
        root = folder / name
        payload = load(ROOT / 'assets/models/alliance_frigate.mesh.json')
        manifest = load(ROOT / 'assets/models/manifests/alliance_frigate.json')
        asset = f's08test:{name}/frigate'
        payload.pop('schema')
        payload.update(contract='star-armada/mesh-export', contract_major=1, asset=asset)
        payload['vertices'] = [[v * scale for v in point] for point in payload['vertices']]
        payload['bounds'] = [[fn(p[i] for p in payload['vertices']) for i in range(3)]
                             for fn in (min, max)]
        path = root / 'frigate.mesh.json'
        dump(path, payload)
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        manifest.pop('approval', None)
        manifest['export'].pop('legacy_schema_int', None)
        manifest.update(asset=asset, display_name=f'S08 test derivative {name}',
                        bounds=dict(zip(('min', 'max'), payload['bounds'])))
        manifest['provenance']['notes'] = 'Test-only uniform-scale derivative; not owner approved.'
        manifest['files'] = {'mesh': {'path': path.name, 'bytes': path.stat().st_size,
                                      'sha256': digest}}
        manifest['revision'] = hashlib.sha256(f'{asset}\nmesh:{digest}'.encode()).hexdigest()
        dump(root / 'manifest.json', manifest)
        dump(root / 'visual-pack.json', {
            'contract': 'star-armada/visual-pack', 'contract_major': 1,
            'id': f's08test:{name}', 'version': '1.0.0',
            'requires': {'min_engine': '0.15.1', 'contracts': ['star-armada/model-manifest/v1']},
            'content': {'replaces': [{'binding': 'rebel:frigate', 'manifest': 'manifest.json'}]}})


def select_visual(mode, packs):
    from render import asset_selection as selection
    from render.asset_registry import AssetResolver
    settings = {'model_preview': mode != 'legacy',
                'visual_packs': [mode] if mode in ('amber', 'blue') else []}
    info = selection.configure(settings, asset_root=ROOT, pack_root=packs)
    mesh = selection.mesh_for('rebel:frigate')
    if mode == 'legacy':
        assert mesh is None, info
        return dict(selection=info, payload_sha256=None, mesh_sha256=None)
    assert mesh is not None, info
    assert selection.selected_binding('rebel:frigate'), info
    # Probe the public resolver as well as the process-global renderer seam.
    resolver = AssetResolver(ROOT)
    if settings['visual_packs']:
        assert all(row['accepted'] for row in info['pack_order']), info
        accepted = resolver.activate_packs([packs / mode / 'visual-pack.json'], pack_root=packs)
        assert accepted == (f's08test:{mode}',), resolver.diagnostics
    resolved = resolver.resolve('rebel:frigate')
    assert resolved is not None and resolved.mesh == mesh
    assert sum(len(batch) for batch in mesh.values()) > 7000
    manifest = load((packs / mode / 'manifest.json') if mode in ('amber', 'blue')
                    else ROOT / 'assets/models/manifests/alliance_frigate.json')
    return dict(selection=info, asset=resolved.asset, revision=resolved.revision,
                payload_sha256=manifest['files']['mesh']['sha256'],
                mesh_sha256=hashlib.sha256(repr(mesh).encode()).hexdigest(),
                triangles=sum(len(batch) for batch in mesh.values()))


def strip_historical(state):
    state = copy.deepcopy(state)
    state.pop('runtime_state')
    removed = 0
    for entity in state['entities'].values():
        for key in HISTORICAL_FIELDS:
            removed += key in entity
            entity.pop(key, None)
        entity.get('systems', {}).pop('life_support', None)
    assert removed > 0
    return state


def fixture_ship(gm, owner=0):
    from game.core.vectors import Vec3
    # Explicit controlled gameplay fixture: each peer creates the same real
    # production ship before launch tick zero; no visual geometry drives state.
    return gm.factory.spawn_ship('rebel_frigate', owner, Vec3(-6000 + owner * 12000, 0, -4500))


def command_for(gm, ship_id, owner, index, legacy_tail=False):
    from game.core.commands import PlayerCommand
    ship = gm.state.entities[ship_id]
    if index in (0, 90):
        return PlayerCommand('move', owner, unit_ids=(ship_id,),
                             target_pos=(ship.pos.x + (350 if owner == 0 else -350),
                                         ship.pos.y, ship.pos.z + 125))
    if index == 45:
        return PlayerCommand('hold', owner, unit_ids=(ship_id,))
    if index == 150 or (legacy_tail and index == STEPS - 1):
        return PlayerCommand('stop', owner, unit_ids=(ship_id,))
    return None


def snapshot(gm):
    from game.net.lan import canonical_state, precise_checksum
    from game.net.replay import state_checksum
    # Compare both precise production save codec and the full LAN future graph,
    # not merely hashes. Canonical graph includes all future AI/system state.
    return dict(tick=gm.state.tick, save=normalized(gm.state.to_dict(precise=True)),
                authoritative=canonical_state(gm), lan_checksum=precise_checksum(gm),
                replay_checksum=state_checksum(gm.state))


def write_trace(stream, gm):
    stream.write(json.dumps(snapshot(gm), sort_keys=True, separators=(',', ':')) + '\n')


def prepare(folder):
    import game.core
    from game.core.manager import GameManager
    from game.core.state import GameState
    from game.data.store import DataStore
    from game.net.replay import MatchRecording, ReplayRecorder
    gm = GameManager.start_skirmish(DataStore.get().maps['skirmish01'])
    ship = fixture_ship(gm)
    for _ in range(37):
        gm.step(DT)
    # Same to_dict()/JSON codec as ordinary quicksave, without main/UI/user paths.
    dump(folder / 'modern-save.json', gm.state.to_dict())
    old = strip_historical(normalized(gm.state.to_dict(precise=True)))
    dump(folder / 'legacy-save.json', old)
    old_gm = GameManager(GameState.from_dict(load(folder / 'legacy-save.json')))
    assert old_gm.ai.ais == {}, 'legacy fresh/lazy AI fallback changed'
    assert old_gm.trading._timer == 0
    restored_ship = old_gm.state.entities[ship.id]
    assert restored_ship.sensor_range == old_gm.ds.ships['rebel_frigate'].sensor_range
    assert restored_ship.upgrade_level == 1 and restored_ship.collection_point is None
    assert restored_ship.crew == restored_ship.max_crew > 0
    assert 'life_support' in restored_ship.systems
    dump(folder / 'fixture.json', dict(ship_id=ship.id, start_tick=gm.state.tick,
                                      fields_removed=list(HISTORICAL_FIELDS),
                                      generated_not_historical_user_file=True))
    for label, manager in [('modern', gm), ('legacy', old_gm)]:
        rec = MatchRecording(manager) if label == 'modern' else ReplayRecorder(manager.state)
        if label == 'legacy':
            manager.state._recorder = rec
        with gzip.open(folder / f'{label}-expected.jsonl.gz', 'wt') as trace:
            write_trace(trace, manager)
            for index in range(STEPS):
                cmd = command_for(manager, ship.id, 0, index, legacy_tail=True)
                if cmd:
                    manager.state.queue_command(cmd)
                manager.step(DT)
                write_trace(trace, manager)
        rec.save(folder / f'{label}-replay.json')
        if label == 'legacy':
            legacy_recording = load(folder / 'legacy-replay.json')
            legacy_recording['initial_state'] = strip_historical(legacy_recording['initial_state'])
            dump(folder / 'legacy-replay.json', legacy_recording)
        if label == 'modern':
            rec.close()


def history_worker(folder, mode, kind):
    import game.core
    from game.core.manager import GameManager
    from game.core.state import GameState
    from game.net.replay import PlaybackSession, load_replay, content_digest
    from game.net.lan import content_hash
    visual = select_visual(mode, folder / 'packs')
    metadata = load(folder / 'fixture.json')
    label, source = kind.split('-')
    if source == 'replay':
        data = load_replay(folder / f'{kind}.json')
        playback = PlaybackSession(data)  # compatibility enabled, never bypassed
        gm = playback.gm
        if label == 'legacy':
            assert 'future' in data['compatibility_warning']
            assert 'duration' in data['compatibility_warning']
            assert playback.end_tick == metadata['start_tick'] + STEPS
    else:
        gm = GameManager(GameState.from_dict(load(folder / f'{kind}.json')))
        playback = None
    position = gm.state.entities[metadata['ship_id']].pos
    before = (position.x, position.y, position.z)
    path = folder / f'{mode}-{kind}.jsonl.gz'
    with gzip.open(path, 'wt') as trace:
        write_trace(trace, gm)
        for index in range(STEPS):
            if playback:
                assert playback.step(), (kind, index)
            else:
                cmd = command_for(gm, metadata['ship_id'], 0, index, legacy_tail=True)
                if cmd:
                    gm.state.queue_command(cmd)
                gm.step(DT)
            write_trace(trace, gm)
    ship = gm.state.entities[metadata['ship_id']]
    after = (ship.pos.x, ship.pos.y, ship.pos.z)
    assert before != after, 'move commands had no effect'
    assert ship.order_type == 'idle', ship.order_type
    assert not gm.state.command_queue
    if playback:
        assert playback.ended and not playback.step()
    dump(folder / f'{mode}-{kind}-report.json', dict(
        visual=visual, trace=str(path), ticks_compared=STEPS + 1,
        content_hash=content_hash(gm.ds), replay_content_digest=content_digest(gm.ds),
        start_position=before, final_position=after, final_order=ship.order_type,
        warning=data.get('compatibility_warning') if playback else None))


def peer_worker(folder, mode, role, port):
    import game.core
    from game.core.manager import GameManager
    from game.net.lan import LanSession, default_lan_options, content_hash, INPUT_DELAY
    from game.net.replay import MatchRecording, content_digest
    visual = select_visual(mode, folder / 'packs')
    options = default_lan_options()
    options.update(map_id='skirmish04', ai_count=1, factions=['rebel', 'imperial', 'syndicate', 'imperial'])
    session = (LanSession.host(port, options) if role == 'host'
               else LanSession.join('127.0.0.1', port))
    deadline = time.monotonic() + 45
    try:
        if role == 'host':
            dump(folder / 'host-ready.json', {'port': session.port})
        ready = False
        while session.launch is None:
            session.poll()
            assert session.snapshot['status'] != 'error', session.snapshot
            assert time.monotonic() < deadline, session.snapshot
            if session.snapshot['status'] == 'lobby' and len(session.snapshot['players']) == 2 and not ready:
                session.set_ready(True)
                ready = True
            if role == 'host' and session.snapshot['can_start']:
                session.start()
            time.sleep(.001)
        gm = GameManager.start_skirmish(session.launch['map_def'])
        ships = [fixture_ship(gm, owner) for owner in (0, 1)]
        gm.state._net_session = session
        rec = MatchRecording(gm, mode='lan', local_player=session.local_player)
        ship = ships[session.local_player]
        before = (ship.pos.x, ship.pos.y, ship.pos.z)
        submitted = set()
        observations = {}
        trace_path = folder / f'{role}.jsonl.gz'
        with gzip.open(trace_path, 'wt') as trace:
            write_trace(trace, gm)
            while gm.state.tick < STEPS:
                tick = gm.state.tick
                if tick not in submitted:
                    cmd = command_for(gm, ship.id, session.local_player, tick)
                    if cmd:
                        gm.state.queue_command(cmd)
                    submitted.add(tick)
                if session.advance(gm, DT):
                    observations[str(gm.state.tick)] = {str(e.id): e.order_type for e in ships}
                    write_trace(trace, gm)
                assert session.snapshot['status'] == 'running', session.snapshot
                assert time.monotonic() < deadline, session.snapshot
                time.sleep(.001)
        rec.close()
        rec.save(folder / f'{role}-replay.json')
        commands = rec.to_dict()['commands']
        assert len(commands) == 8, commands
        assert [entry['tick'] for entry in commands] == [
            t + INPUT_DELAY for t in (0, 45, 90, 150) for _ in (0, 1)], commands
        assert [entry['cmd']['player'] for entry in commands] == [0, 1] * 4
        for t, order in ((0, 'move'), (45, 'hold'), (90, 'move'), (150, 'idle')):
            assert set(observations[str(t + INPUT_DELAY + 1)].values()) == {order}, observations
        after = (ship.pos.x, ship.pos.y, ship.pos.z)
        assert before != after and ship.order_type == 'idle'
        dump(folder / f'{role}-report.json', dict(
            pid=os.getpid(), role=role, visual=visual, trace=str(trace_path),
            ticks_compared=STEPS + 1, content_hash=content_hash(gm.ds),
            replay_content_digest=content_digest(gm.ds), commands=commands,
            start_position=before, final_position=after, final_order=ship.order_type,
            status=session.snapshot['status']))
        # Keep the live TCP session serviced until BOTH processes captured state.
        dump(folder / f'{role}-done.json', {'tick': gm.state.tick})
        other = 'client' if role == 'host' else 'host'
        while not (folder / f'{other}-done.json').exists():
            session.poll()
            assert time.monotonic() < deadline, session.snapshot
            time.sleep(.001)
    finally:
        session.close()


def first_difference(a, b, path='$'):
    if type(a) is not type(b):
        return f'{path}: types {type(a).__name__} != {type(b).__name__}'
    if isinstance(a, dict):
        if a.keys() != b.keys():
            return f'{path}: keys {a.keys() ^ b.keys()}'
        for key in a:
            difference = first_difference(a[key], b[key], f'{path}.{key}')
            if difference:
                return difference
    elif isinstance(a, list):
        if len(a) != len(b):
            return f'{path}: lengths {len(a)} != {len(b)}'
        for index, (left, right) in enumerate(zip(a, b)):
            difference = first_difference(left, right, f'{path}[{index}]')
            if difference:
                return difference
    elif a != b:
        return f'{path}: {a!r} != {b!r}'
    return None


class CosmeticCompatibilityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temporary = tempfile.TemporaryDirectory(prefix='s08-cosmetic-', dir=SCRATCH)
        cls.folder = Path(cls.temporary.name)
        make_packs(cls.folder / 'packs')
        cls.addClassCleanup(cls.temporary.cleanup)
        cls.evidence = {'limits': __doc__, 'history': [], 'lan': {}, 'negative_control': {},
                        'completed_gates': [], 'trajectories': {}}
        cls.run_worker('prepare')
        cls.evidence['fixture'] = load(cls.folder / 'fixture.json')

    @classmethod
    def tearDownClass(cls):
        output = os.environ.get('S08_COSMETIC_EVIDENCE')
        if output:
            evidence = dict(cls.evidence)
            trajectories = evidence.pop('trajectories')
            evidence['all_gates_completed'] = len(evidence['completed_gates']) == 3
            evidence['trajectory_file'] = 'tick-checksums.json'
            dump(Path(output) / 'summary.json', evidence)
            dump(Path(output) / 'tick-checksums.json', trajectories)

    @classmethod
    def worker_command(cls, *args):
        return [sys.executable, str(Path(__file__).resolve()), '--worker',
                str(cls.folder), *map(str, args)]

    @classmethod
    def run_worker(cls, *args):
        result = subprocess.run(cls.worker_command(*args), cwd=ROOT,
                                env=dict(os.environ, PYTHONPATH=os.pathsep.join((str(ROOT / 'tests'), str(ROOT))),
                                         PYTHONDONTWRITEBYTECODE='1'),
                                text=True, capture_output=True, timeout=100)
        if result.returncode:
            raise AssertionError(f'worker {args}: exit {result.returncode}\n{result.stdout}\n{result.stderr}')
        return result

    def compare_traces(self, left, right):
        from itertools import zip_longest
        count = 0
        trajectory = []
        with gzip.open(left, 'rt') as a, gzip.open(right, 'rt') as b:
            for index, (aa, bb) in enumerate(zip_longest(a, b)):
                self.assertIsNotNone(aa, f'left trace ended at {index}')
                self.assertIsNotNone(bb, f'right trace ended at {index}')
                lhs, rhs = json.loads(aa), json.loads(bb)
                if lhs != rhs:
                    self.fail(f'tick {lhs["tick"]}: {first_difference(lhs, rhs)}')
                trajectory.append(dict(tick=rhs['tick'], lan_checksum=rhs['lan_checksum'],
                                       replay_checksum=rhs['replay_checksum'],
                                       full_snapshot_sha256=hashlib.sha256(
                                           json.dumps(rhs, sort_keys=True, separators=(',', ':')).encode()).hexdigest()))
                count += 1
        self.assertEqual(count, STEPS + 1)
        self.evidence['trajectories'][Path(right).name] = trajectory
        return count

    def test_legacy_and_current_save_replay_continuation_across_visual_selections(self):
        reports = []
        for mode in ('legacy', 'core', 'amber', 'blue'):
            for kind in ('modern-save', 'modern-replay', 'legacy-save', 'legacy-replay'):
                with self.subTest(mode=mode, kind=kind):
                    self.run_worker('history', mode, kind)
                    report = load(self.folder / f'{mode}-{kind}-report.json')
                    label = kind.split('-')[0]
                    self.compare_traces(self.folder / f'{label}-expected.jsonl.gz', report['trace'])
                    report.update(mode=mode, kind=kind, exact_every_tick=True)
                    report.pop('trace')
                    reports.append(report)
        self.assertEqual(len(reports), 16)
        self.assertEqual(len({r['content_hash'] for r in reports}), 1)
        self.assertEqual(len({r['replay_content_digest'] for r in reports}), 1)
        self.assertEqual(len({r['visual']['mesh_sha256'] for r in reports}), 4)
        self.evidence['history'] = reports
        self.evidence['completed_gates'].append('history')

    def test_two_live_production_lan_peers_different_real_visual_payloads(self):
        with socket.socket() as reservation:
            reservation.bind(('127.0.0.1', 0))
            port = reservation.getsockname()[1]
        env = dict(os.environ, PYTHONPATH=os.pathsep.join((str(ROOT / 'tests'), str(ROOT))), PYTHONDONTWRITEBYTECODE='1')
        processes = []
        try:
            host = subprocess.Popen(self.worker_command('peer', 'amber', 'host', port),
                                    cwd=ROOT, env=env, stdout=subprocess.PIPE,
                                    stderr=subprocess.PIPE, text=True)
            processes.append(host)
            deadline = time.monotonic() + 15
            while not (self.folder / 'host-ready.json').exists():
                if host.poll() is not None:
                    stdout, stderr = host.communicate()
                    self.fail(f'host failed {host.returncode}\n{stdout}\n{stderr}')
                self.assertLess(time.monotonic(), deadline, 'host did not open listener')
                time.sleep(.01)
            client = subprocess.Popen(self.worker_command('peer', 'blue', 'client', port),
                                      cwd=ROOT, env=env, stdout=subprocess.PIPE,
                                      stderr=subprocess.PIPE, text=True)
            processes.append(client)
            for role, process in zip(('host', 'client'), processes):
                stdout, stderr = process.communicate(timeout=75)
                self.assertEqual(process.returncode, 0, f'{role}\n{stdout}\n{stderr}')
            a, b = [load(self.folder / f'{role}-report.json') for role in ('host', 'client')]
            self.assertNotEqual(a['pid'], b['pid'])
            self.assertNotEqual(a['visual']['payload_sha256'], b['visual']['payload_sha256'])
            self.assertNotEqual(a['visual']['mesh_sha256'], b['visual']['mesh_sha256'])
            self.assertEqual(a['content_hash'], b['content_hash'])
            self.assertEqual(a['replay_content_digest'], b['replay_content_digest'])
            self.assertEqual(a['commands'], b['commands'])
            count = self.compare_traces(a['trace'], b['trace'])
            for report in (a, b):
                report.pop('trace')
            self.evidence['lan'] = dict(host=a, client=b, exact_every_tick=True,
                                        compared_snapshots=count, transport='production TCP loopback')
            self.evidence['completed_gates'].append('live_lan')
        finally:
            for process in processes:
                if process.poll() is None:
                    process.kill()
                    process.communicate()

    def test_gameplay_changing_mod_is_still_incompatible(self):
        import game.core
        from game.data import store
        from game.core.manager import GameManager
        from game.net.lan import content_hash
        from game.net.replay import MatchRecording, PlaybackSession, content_digest, load_replay
        previous = store.DataStore._instance
        root = self.folder / 'mod-fixture'
        path = root / 'mods/s08_changed/data/ships/rebel.json'
        payload = load(ROOT / 'assets/data/ships/rebel.json')
        original = payload['ships']['rebel_frigate']['hull']
        payload['ships']['rebel_frigate']['hull'] = original + 123
        dump(path, payload)
        try:
            baseline = store.DataStore()
            with patch.object(store, 'ROOT', str(root)), patch.dict(
                    os.environ, STAR_ARMADA_DATA=str(ROOT / 'assets/data')):
                modded = store.DataStore(mods=['s08_changed'])
                self.assertEqual(modded.ships['rebel_frigate'].hull, original + 123)
                self.assertNotEqual(content_digest(baseline), content_digest(modded))
                with self.assertRaisesRegex(ValueError, 'LAN does not support mods') as lan_error:
                    content_hash(modded)
                gm = GameManager(mods=['s08_changed'])
                gm.load_map(gm.ds.maps['skirmish01'])
                rec = MatchRecording(gm, mods=['s08_changed'])
                gm.step(DT)
                replay_path = root / 'modded-replay.json'
                rec.save(replay_path)
                rec.close()
                # Identical mod payload is allowed for replay, never for LAN.
                self.assertTrue(PlaybackSession(load_replay(replay_path)).step())
                payload['ships']['rebel_frigate']['hull'] = original + 456
                dump(path, payload)
                with self.assertRaisesRegex(ValueError, 'content/mods are incompatible') as replay_error:
                    PlaybackSession(load_replay(replay_path))
                self.evidence['negative_control'] = dict(
                    original_hull=original, recorded_mod_hull=original + 123,
                    changed_mod_hull=original + 456, lan_rejection=str(lan_error.exception),
                    replay_rejection=str(replay_error.exception), same_mod_replay_accepted=True)
                self.evidence['completed_gates'].append('gameplay_mod_negative_control')
        finally:
            store.DataStore._instance = previous


if __name__ == '__main__':
    if len(sys.argv) > 1 and sys.argv[1] == '--worker':
        folder, action, *args = sys.argv[2:]
        folder = Path(folder)
        if action == 'prepare':
            prepare(folder)
        elif action == 'history':
            history_worker(folder, *args)
        elif action == 'peer':
            mode, role, port = args
            peer_worker(folder, mode, role, int(port))
        else:
            raise ValueError(action)
    else:
        unittest.main()
