import unittest
import socket
import time


def free_port():
    with socket.socket() as s:
        s.bind(('127.0.0.1', 0))
        return s.getsockname()[1]


def pump(sessions, predicate, seconds=3):
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        for session in sessions:
            session.poll()
        if predicate():
            return
        time.sleep(.001)
    raise AssertionError([s.snapshot for s in sessions])


class LobbyTests(unittest.TestCase):
    def test_inflight_ready_cannot_consent_to_new_configuration(self):
        h, c = SimulationTests().sessions(launch=False)
        self.addCleanup(h.close)
        self.addCleanup(c.close)
        c.set_ready(True)  # queued before host changes the configuration
        options = h.snapshot['options']
        options['ai_difficulty'] = 'hard'
        h.configure(options)
        h.set_ready(True)
        for _ in range(20):
            h.poll()
            c.poll()
        self.assertFalse(h.snapshot['can_start'])
        self.assertFalse(h.snapshot['players'][1]['ready'])
        self.assertEqual(c.snapshot['revision'], h.snapshot['revision'])
        c.set_ready(True)
        pump([h, c], lambda: h.snapshot['can_start'])

    def test_real_tcp_three_humans_ready_configure_start(self):
        from game.net.lan import LanSession, default_lan_options
        opts = default_lan_options()
        opts.update(map_id='skirmish04', human_count=3, ai_count=1)
        host = LanSession.host(free_port(), opts)
        self.addCleanup(host.close)
        clients = [LanSession.join('127.0.0.1', host.snapshot['port'], name=f'Client{i}') for i in range(2)]
        for c in clients:
            self.addCleanup(c.close)
        sessions = [host] + clients
        pump(sessions, lambda: all(len(s.snapshot['players']) == 3 for s in sessions))
        self.assertEqual(sorted(c.local_player for c in clients), [1, 2])
        self.assertFalse(host.snapshot['can_start'])
        with self.assertRaises(ValueError):
            host.start()
        for s in sessions:
            s.set_ready(True)
        pump(sessions, lambda: host.snapshot['can_start'])
        host.configure(opts)
        self.assertFalse(host.snapshot['can_start'])
        pump(sessions, lambda: all(not any(p['ready'] for p in s.snapshot['players']) for s in sessions))
        for s in sessions:
            s.set_ready(True)
        pump(sessions, lambda: host.snapshot['can_start'])
        host.start()
        pump(sessions, lambda: all(s.launch is not None for s in sessions))
        self.assertTrue(all(s.launch['map_def'] == host.launch['map_def'] for s in clients))
        with self.assertRaises(ValueError):
            clients[0].configure(opts)

    def test_start_resets_lobby_clock_and_reports_lan_address(self):
        from game.net.lan import TIMEOUT
        from game.core.manager import GameManager
        h, c = SimulationTests().sessions(launch=False)
        self.addCleanup(h.close)
        self.addCleanup(c.close)
        h._progress -= TIMEOUT*2
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as probe:
            try:
                probe.connect(('192.0.2.1', 1))  # Routing lookup only; sends nothing.
                address = probe.getsockname()[0]
            except OSError:
                address = '127.0.0.1'
        self.assertIn(address, h.snapshot['addresses'])
        h.start()
        gm = GameManager.start_skirmish(h.launch['map_def'])
        self.assertFalse(h.advance(gm, 1/30))
        self.assertEqual(h.snapshot['status'], 'running')

    def test_port_validation_and_in_use(self):
        from game.net.lan import LanSession, default_lan_options
        for port in (0, 65536, True, '7777'):
            with self.assertRaises(ValueError):
                LanSession.host(port, default_lan_options())
            with self.assertRaises(ValueError):
                LanSession.join('127.0.0.1', port)
        h = LanSession.host(free_port(), default_lan_options())
        self.addCleanup(h.close)
        with self.assertRaises(OSError):
            LanSession.host(h.snapshot['port'], default_lan_options())

from copy import deepcopy
from game.data.store import DataStore


class TransportTests(unittest.TestCase):
    def test_parser_limits_messages_per_poll_and_preserves_remainder(self):
        from game.net.lan import _Peer
        with socket.socket() as listener:
            listener.bind(('127.0.0.1', 0))
            listener.listen()
            with socket.create_connection(listener.getsockname()) as raw:
                accepted, _ = listener.accept()
                with accepted:
                    sender, receiver = _Peer(raw), _Peer(accepted)
                    for i in range(70):
                        sender.send(dict(type='probe', index=i))
                    sender.flush()
                    messages = []
                    deadline = time.monotonic()+3
                    while len(messages) < 70 and time.monotonic() < deadline:
                        batch = receiver.poll()
                        self.assertLessEqual(len(batch), 32)
                        messages.extend(batch)
                    self.assertEqual([m['index'] for m in messages], list(range(70)))

    def test_real_tcp_delayed_reads_partial_headers_short_writes(self):
        from game.net.lan import _Peer, MAX_BUFFER
        class ShortSocket:
            def __init__(self, sock):
                self.sock = sock
            def __getattr__(self, key):
                return getattr(self.sock, key)
            def send(self, data):
                return self.sock.send(data[:3])
            def recv(self, size):
                return self.sock.recv(min(size, 2))
        with socket.socket() as listener:
            listener.bind(('127.0.0.1', 0))
            listener.listen()
            with socket.create_connection(listener.getsockname()) as raw:
                accepted, _ = listener.accept()
                with accepted:
                    sender, receiver = _Peer(ShortSocket(raw)), _Peer(ShortSocket(accepted))
                    data = dict(type='probe', payload='x'*2000)
                    sender.send(data)
                    for _ in range(25):
                        self.assertEqual(sender.poll(), [])
                    messages = []
                    deadline = time.monotonic()+3
                    while not messages and time.monotonic() < deadline:
                        sender.poll()
                        messages.extend(receiver.poll())
                    self.assertEqual(messages, [data])
                    self.assertFalse(sender.tx)
                    with self.assertRaises(ValueError):
                        sender.send(dict(payload='x'*MAX_BUFFER))


class ProtocolTests(unittest.TestCase):
    def test_unjoined_tcp_probes_cannot_kill_lobby_or_running_match(self):
        import struct
        h, c = SimulationTests().sessions(launch=False)
        self.addCleanup(h.close)
        self.addCleanup(c.close)
        for running in (False, True):
            if running:
                h.start()
                pump([h, c], lambda: c.launch is not None)
            for payload in (b'', struct.pack('!I', 1)+b'{',
                            struct.pack('!I', 32)+b'{"type":"hello","version":"bad"}'):
                with socket.create_connection(('127.0.0.1', h.port)) as probe:
                    # Connect completion does not guarantee accept readiness.
                    pump([h, c], lambda: len(h._peers) == 2)
                    if payload:
                        probe.sendall(payload)
                # EOF/malformed-frame delivery is asynchronous, not ten polls.
                pump([h, c], lambda: len(h._peers) == 1)
                self.assertEqual(h.snapshot['status'], 'running' if running else 'lobby')
                self.assertEqual(len(h._peers), 1)

    def test_joined_timeout_stops_match_without_waiting(self):
        from game.net.lan import TIMEOUT
        from game.core.manager import GameManager
        h, c = SimulationTests().sessions()
        managers = [GameManager.start_skirmish(s.launch['map_def']) for s in (h, c)]
        for _ in range(1000):
            for s, gm in zip((h, c), managers):
                if gm.state.tick == 0:
                    s.advance(gm, 1/30)
                else:
                    s.poll()
            if all(gm.state.tick == 1 for gm in managers):
                break
        self.assertEqual([gm.state.tick for gm in managers], [1, 1])
        h._peers[0].last -= TIMEOUT*2
        start = time.monotonic()
        h.poll()
        self.assertLess(time.monotonic()-start, .1)
        self.assertEqual(h.snapshot['status'], 'error')
        self.assertIn('timeout', h.snapshot['error'].lower())
        h.close()
        c.close()

    def test_handshake_rejects_version_protocol_content_and_mods(self):
        from game.net.lan import LanSession, default_lan_options
        for field in ('version', 'protocol', 'content'):
            with self.subTest(field=field):
                h = LanSession.host(free_port(), default_lan_options())
                c = LanSession.join('127.0.0.1', h.port)
                self.addCleanup(h.close)
                self.addCleanup(c.close)
                import json, struct
                p = c._peers[0]
                size = struct.unpack('!I', p.tx[:4])[0]
                hello = json.loads(p.tx[4:4+size])
                hello[field] = 'wrong'
                p.tx.clear()
                p.send(hello)
                pump([h, c], lambda: c.snapshot['status'] == 'error')
                self.assertEqual(h.snapshot['status'], 'lobby')
                self.assertEqual(len(h.snapshot['players']), 1)
        ds = DataStore.get()
        ds.mod_files['fake'] = '{}'
        try:
            with self.assertRaises(ValueError):
                LanSession.host(free_port(), default_lan_options())
        finally:
            ds.mod_files.clear()

    def test_commands_reject_missing_fields_counts_and_nonfinite(self):
        from game.net.lan import _commands, MAX_COMMANDS
        for d in (dict(type='move', player=1),
                  dict(type='build_ship', player=1, unit_ids=[1], ship_id='x', name='9'*100),
                  dict(type='attack', player=1),
                  dict(type='move', player=1, target_pos=[float('nan'),0,0])):
            with self.subTest(command=d), self.assertRaises(ValueError):
                _commands([d], 1)
        with self.assertRaises(ValueError):
            _commands([dict(type='stop', player=1)]*(MAX_COMMANDS+1), 1)

    def test_duplicate_json_keys_and_invalid_lobby_or_start_are_rejected(self):
        from game.net.lan import LanSession, default_lan_options
        import struct
        h = LanSession.host(free_port(), default_lan_options())
        self.addCleanup(h.close)
        raw = b'{"type":"hello","type":"hello"}'
        with socket.create_connection(('127.0.0.1', h.port)) as sock:
            sock.sendall(struct.pack('!I', len(raw)) + raw)
            h.poll()
            pump([h], lambda: not h._peers)
            self.assertEqual(h.snapshot['status'], 'lobby')
        for malicious in (dict(type='lobby', options=default_lan_options(), players=[dict(slot=99,name='bad',ready=True)]),
                          dict(type='start', map_def={'players': []})):
            sessions = SimulationTests().sessions(launch=False)  # cleanup explicitly below
            h, c = sessions
            try:
                h._peers[0].send(malicious)
                pump(sessions, lambda: c.snapshot['status'] == 'error')
            finally:
                for s in sessions:
                    s.close()

    def test_heartbeat_keeps_idle_lobby_alive(self):
        from game.net.lan import LanSession, default_lan_options, TIMEOUT
        h = LanSession.host(free_port(), default_lan_options())
        c = LanSession.join('127.0.0.1', h.port)
        self.addCleanup(h.close)
        self.addCleanup(c.close)
        pump([h,c], lambda: len(c.snapshot['players']) == 2)
        for s in (h,c):
            s._heartbeat -= TIMEOUT
        pump([h,c], lambda: all(not p.tx for s in (h,c) for p in s._peers))
        self.assertEqual(h.snapshot['status'], 'lobby')
        self.assertEqual(c.snapshot['status'], 'lobby')

    def test_malformed_frames_disconnect_and_timeout_are_fatal_nonblocking(self):
        from game.net.lan import LanSession, default_lan_options, MAX_FRAME
        import struct
        for payload in (struct.pack('!I', MAX_FRAME+1), struct.pack('!I', 2)+b'[]',
                        struct.pack('!I', 1)+b'{'):
            h = LanSession.host(free_port(), default_lan_options())
            self.addCleanup(h.close)
            with socket.create_connection(('127.0.0.1', h.port)) as s:
                s.sendall(payload)
                h.poll()
                pump([h], lambda: not h._peers)
                self.assertEqual(h.snapshot['status'], 'lobby')
        h = LanSession.host(free_port(), default_lan_options())
        c = LanSession.join('127.0.0.1', h.port)
        self.addCleanup(h.close)
        self.addCleanup(c.close)
        pump([h, c], lambda: c.snapshot['status'] == 'lobby')
        c.close()
        pump([h], lambda: h.snapshot['status'] == 'error')
        h = LanSession.host(free_port(), default_lan_options())
        self.addCleanup(h.close)
        with socket.create_connection(('127.0.0.1', h.port)):
            # Wait for accept before inspecting the unjoined peer's timeout.
            pump([h], lambda: len(h._peers) == 1)
            h._peers[0].last -= 100
            start = time.monotonic()
            h.poll()
            self.assertLess(time.monotonic()-start, .1)
            self.assertEqual(h.snapshot['status'], 'lobby')
            self.assertFalse(h._peers)


class LoadingTests(unittest.TestCase):
    def test_loading_deadline_is_absolute_despite_heartbeats_and_polls(self):
        from game.net.lan import LOADING_TIMEOUT
        now = [100.]
        h, c = self.sessions(now)
        h.start()
        for _ in range(1000):
            h.poll()
            c.poll()
            if c.launch is not None:
                break
        self.assertIsNotNone(c.launch)
        for elapsed in range(5, int(LOADING_TIMEOUT) + 1, 5):
            now[0] = 100. + elapsed
            for _ in range(10):
                h.poll()
                c.poll()
            self.assertEqual(h.snapshot['status'], 'running')
            self.assertEqual(c.snapshot['status'], 'running')
        now[0] = 100. + LOADING_TIMEOUT + .1
        h.poll()
        self.assertEqual(h.snapshot['status'], 'error')
        self.assertIn('Loading timeout', h.snapshot['error'])

    def test_joined_disconnect_is_fatal_during_loading(self):
        now = [100.]
        h, c = self.sessions(now)
        h.start()
        c.close()
        for _ in range(1000):
            h.poll()
            if h.snapshot['status'] == 'error':
                break
        self.assertEqual(h.snapshot['status'], 'error')
        self.assertTrue(any(word in h.snapshot['error'].lower()
                            for word in ('disconnect', 'reset', 'broken pipe')), h.snapshot)

    def sessions(self, now):
        from unittest.mock import patch
        from game.net.lan import LanSession, default_lan_options
        clock = patch('game.net.lan.time.monotonic', side_effect=lambda: now[0])
        clock.start()
        self.addCleanup(clock.stop)
        h = LanSession.host(free_port(), default_lan_options())
        c = LanSession.join('127.0.0.1', h.port)
        for s in (h, c):
            self.addCleanup(s.close)
        for _ in range(1000):
            h.poll()
            c.poll()
            if len(c.snapshot['players']) == 2:
                break
        self.assertEqual(len(c.snapshot['players']), 2)
        h.set_ready(True)
        c.set_ready(True)
        for _ in range(1000):
            h.poll()
            c.poll()
            if h.snapshot['can_start']:
                break
        self.assertTrue(h.snapshot['can_start'])
        return h, c

    def test_launch_flush_and_two_cold_graphs_survive_25_seconds_each(self):
        from game.core.manager import GameManager
        from game.net.lan import TIMEOUT, precise_checksum
        now = [100.]
        h, c = self.sessions(now)
        h.start()
        # Host graph blocks without another host poll. The client resumes after
        # its old lobby receive timestamp has exceeded the gameplay timeout.
        now[0] += 25
        for _ in range(1000):
            c.poll()  # TCP delivery may require another nonblocking receive.
            if c.launch is not None or c.snapshot['status'] == 'error':
                break
        self.assertIsNotNone(c.launch, c.snapshot)
        hg = GameManager.start_skirmish(h.launch['map_def'])
        self.assertFalse(h.advance(hg, 1/30))
        now[0] += 25
        cg = GameManager.start_skirmish(c.launch['map_def'])
        self.assertEqual(hg.state.tick, 0)
        for _ in range(1000):
            for s, gm in ((h, hg), (c, cg)):
                if gm.state.tick == 0:
                    s.advance(gm, 1/30)
                else:
                    s.poll()
            if hg.state.tick == cg.state.tick == 1:
                break
        self.assertEqual((hg.state.tick, cg.state.tick), (1, 1), (h.snapshot, c.snapshot))
        self.assertEqual(precise_checksum(hg), precise_checksum(cg))
        # Heartbeats must not hide stalled simulation after the initial barrier.
        now[0] += TIMEOUT + .1
        h.poll()
        self.assertEqual(h.snapshot['status'], 'error')
        self.assertIn('Lockstep timeout', h.snapshot['error'])


class SimulationTests(unittest.TestCase):
    def test_pipeline_delivers_human_commands_once_after_fixed_delay(self):
        from game.net.lan import INPUT_DELAY, precise_checksum
        from game.core.manager import GameManager
        from game.core.commands import StopCommand
        sessions = self.sessions(ai=1, mid='skirmish04')
        managers = [GameManager.start_skirmish(s.launch['map_def']) for s in sessions]
        observed = [[], []]
        for i, (s, gm) in enumerate(zip(sessions, managers)):
            gm.state._net_session = s
            original = gm.step
            def record(dt, original=original, gm=gm, i=i):
                observed[i].extend((gm.state.tick, cmd.to_dict()) for cmd in gm.state.command_queue
                                   if not gm.state.players[cmd.player].is_ai)
                original(dt)
            gm.step = record
            ship = next(e for e in gm.state.entities.values() if e.owner == s.local_player and e.is_ship)
            gm.state.queue_command(StopCommand(s.local_player, [ship.id]))
        for tick in range(INPUT_DELAY + 8):
            stepped = set()
            deadline = time.monotonic()+3
            while len(stepped) < 2 and time.monotonic() < deadline:
                for i, (s, gm) in enumerate(zip(sessions, managers)):
                    if i not in stepped and s.advance(gm, 100.):
                        stepped.add(i)
            self.assertEqual([gm.state.tick for gm in managers], [tick+1]*2)
            self.assertEqual(precise_checksum(managers[0]), precise_checksum(managers[1]))
        self.assertEqual(observed[0], observed[1])
        self.assertEqual(len(observed[0]), 2)
        self.assertEqual([tick for tick, _ in observed[0]], [INPUT_DELAY]*2)
        self.assertEqual([cmd['player'] for _, cmd in observed[0]], [0, 1])

    def test_joined_sender_cannot_skip_initial_checksum_barrier(self):
        from game.net.lan import INPUT_DELAY
        h, c = self.sessions()
        c._peers[0].send(dict(type='input', tick=INPUT_DELAY, checksum='0'*64, commands=[]))
        pump([h, c], lambda: h.snapshot['status'] == 'error')
        self.assertIn('sequence', h.snapshot['error'])

    def sessions(self, humans=2, ai=0, mid='skirmish01', launch=True):
        from game.net.lan import LanSession, default_lan_options
        opts = default_lan_options()
        opts.update(human_count=humans, ai_count=ai, map_id=mid)
        host = LanSession.host(free_port(), opts)
        sessions = [host] + [LanSession.join('127.0.0.1', host.port) for _ in range(humans-1)]
        for s in sessions:
            self.addCleanup(s.close)
        pump(sessions, lambda: all(len(s.snapshot['players']) == humans for s in sessions))
        for s in sessions:
            s.set_ready(True)
        pump(sessions, lambda: host.snapshot['can_start'])
        if not launch:
            return sessions
        host.start()
        pump(sessions, lambda: all(s.launch for s in sessions))
        return sessions

    def test_real_managers_three_humans_ai_moves_every_tick_and_all_maps(self):
        from game.core.manager import GameManager
        from game.core.commands import MoveCommand
        from game.net.lan import precise_checksum
        for humans, ai, mid in [(3, 1, 'skirmish04')] + [(2, 0, f'skirmish0{i}') for i in range(1,5)]:
            with self.subTest(map=mid, humans=humans):
                sessions = self.sessions(humans, ai, mid)
                managers = [GameManager.start_skirmish(s.launch['map_def']) for s in sessions]
                starts = []
                for s, gm in zip(sessions, managers):
                    gm.state._net_session = s
                    ship = next(e for e in gm.state.entities.values() if e.owner == s.local_player and e.is_ship and not e.is_squadron)
                    starts.append((ship.id, (ship.pos.x, ship.pos.z)))
                    gm.state.queue_command(MoveCommand(s.local_player, [ship.id], (ship.pos.x*.8, 0, ship.pos.z*.8)))
                    self.assertFalse(gm.state.command_queue)
                for tick in range(90):
                    deadline = time.monotonic()+3
                    stepped = set()
                    while len(stepped) < humans and time.monotonic() < deadline:
                        for i, (s, gm) in enumerate(zip(sessions, managers)):
                            if i not in stepped and s.advance(gm, 1/30):
                                stepped.add(i)
                        time.sleep(.0001)
                    self.assertEqual(len(stepped), humans, [s.snapshot for s in sessions])
                    self.assertEqual([gm.state.tick for gm in managers], [tick+1]*humans)
                    self.assertEqual(len({precise_checksum(gm) for gm in managers}), 1)
                for eid, pos in starts:
                    e = managers[0].state.entities[eid]
                    self.assertNotEqual((e.pos.x, e.pos.z), pos)
                if ai:
                    self.assertTrue(managers[0].ai.ais)
                for s in sessions:
                    s.close()

    def test_precise_checksum_covers_future_state_and_excludes_query_caches(self):
        from game.net.lan import precise_checksum
        from game.core.manager import GameManager
        from game.core.commands import StopCommand
        h, c = self.sessions()
        gm = GameManager.start_skirmish(h.launch['map_def'])
        before = precise_checksum(gm)
        gm.state.can_see(0, next(iter(gm.state.entities)))
        self.assertEqual(precise_checksum(gm), before)
        ship = next(e for e in gm.state.entities.values() if e.is_ship)
        ship.jump_charge = .123456789012345
        self.assertNotEqual(precise_checksum(gm), before)
        before = precise_checksum(gm)
        ship.jump_charge += 1e-14
        self.assertNotEqual(precise_checksum(gm), before)
        before = precise_checksum(gm)
        gm.state.command_queue.append(StopCommand(0, [ship.id]))
        self.assertNotEqual(precise_checksum(gm), before)
        before = precise_checksum(gm)
        gm._capacity_timer += 1e-14
        self.assertNotEqual(precise_checksum(gm), before)
        gm2 = GameManager.start_skirmish(c.launch['map_def'])
        self.assertFalse(h.advance(gm, 1/30))
        self.assertFalse(c.advance(gm2, 1/30))
        pump([h,c], lambda: h.snapshot['status'] == 'error')
        self.assertIn('Desync', h.snapshot['error'])
        self.assertEqual(gm.state.tick, 0)
        self.assertEqual(gm2.state.tick, 0)

    def test_four_human_and_two_ai_configurations(self):
        from game.core.manager import GameManager
        from game.net.lan import precise_checksum
        for humans, ai in ((4,0), (2,2)):
            sessions = self.sessions(humans, ai, 'skirmish04')
            managers = [GameManager.start_skirmish(s.launch['map_def']) for s in sessions]
            for gm,s in zip(managers,sessions):
                gm.state._net_session = s
            for tick in range(10):
                stepped = set()
                deadline = time.monotonic()+3
                while len(stepped) < humans and time.monotonic() < deadline:
                    for i,(s,gm) in enumerate(zip(sessions,managers)):
                        s.poll()
                        if i not in stepped and s.advance(gm, 1/30):
                            stepped.add(i)
                self.assertEqual(len(stepped), humans, [s.snapshot for s in sessions])
                self.assertEqual(len({precise_checksum(gm) for gm in managers}), 1)
            for s in sessions:
                s.close()

    def test_wait_does_not_step_and_forged_player_rejected(self):
        from game.core.manager import GameManager
        from game.core.commands import MoveCommand
        sessions = self.sessions()
        h, c = sessions
        gm = GameManager.start_skirmish(h.launch['map_def'])
        self.assertFalse(h.advance(gm, 100))
        self.assertEqual(gm.state.tick, 0)
        with self.assertRaises(ValueError):
            c.submit(MoveCommand(0, [], (0, 0, 0)), 0)
        c._peers[0].send(dict(type='input', tick=0, checksum='0'*64, commands=[MoveCommand(0, [], (0,0,0)).to_dict()]))
        pump(sessions, lambda: h.snapshot['status'] == 'error')
        self.assertIn('ownership', h.snapshot['error'])


class DiagnosticTests(unittest.TestCase):
    def test_independent_processes_compare_every_tick_with_ai_and_moves(self):
        import subprocess, sys, tempfile, json
        from pathlib import Path
        root = Path(__file__).resolve().parents[1]
        with tempfile.TemporaryDirectory() as out:
            result = subprocess.run([sys.executable, str(root/'tools/diag_lan.py'), '--out', out, '--ticks', '180'],
                                    cwd=root, capture_output=True, text=True, timeout=60)
            self.assertEqual(result.returncode, 0, result.stdout+result.stderr)
            reports = [json.loads((Path(out)/f'{role}.json').read_text()) for role in ('host','client')]
            self.assertEqual(reports[0]['checksums'], reports[1]['checksums'])
            self.assertEqual(len(reports[0]['checksums']), 181)
            for r in reports:
                self.assertGreaterEqual(r['ticks_per_second'], 27., {k: v for k, v in r.items() if k != 'checksums'})
                self.assertTrue(r['human_moved'])
                self.assertGreater(r['human_commands'], 1)
                self.assertGreater(r['ai_commands'], 0)
            self.assertIn('DIAG_LAN_OK', result.stdout)


class ContentIdentityTests(unittest.TestCase):
    def test_game_version_has_single_authoritative_import(self):
        import ast
        from pathlib import Path
        tree = ast.parse((Path(__file__).resolve().parents[1]/'game/net/lan.py').read_text())
        self.assertTrue(any(isinstance(n, ast.ImportFrom) and n.module == 'game'
                            and any(a.name == '__version__' and a.asname == 'GAME_VERSION' for a in n.names)
                            for n in tree.body))

    def test_hash_uses_portable_relative_paths(self):
        from game.net.lan import content_hash
        from unittest.mock import patch
        from pathlib import PureWindowsPath
        ds = DataStore.get()
        baseline = content_hash(ds)
        class WindowsFile:
            def __init__(self, path): self.path = path
            def relative_to(self, root): return PureWindowsPath(self.path.relative_to(root))
            def read_text(self): return self.path.read_text()
            def __lt__(self, other): return str(self.path) < str(other.path)
        files = list(__import__('pathlib').Path(ds.assets_dir).rglob('*.json'))
        with patch('game.net.lan.Path') as paths:
            paths.return_value.rglob.return_value = [WindowsFile(p) for p in files]
            self.assertEqual(content_hash(ds), baseline)


class MapTests(unittest.TestCase):
    def test_maps_are_private_validated_human_ai_slots(self):
        from game.net.lan import default_lan_options, build_lan_map
        ds = DataStore()
        before = deepcopy(ds.maps)
        for mid in ('skirmish01', 'skirmish02', 'skirmish03', 'skirmish04'):
            opts = default_lan_options()
            opts['map_id'] = mid
            result = build_lan_map(ds, opts)
            self.assertEqual([p['is_ai'] for p in result['players']], [False, False])
            capacity = len(ds.maps[mid]['players'])
            if capacity >= 4:
                opts.update(human_count=3, ai_count=1, cooperative=True)
                result = build_lan_map(ds, opts)
                self.assertEqual([p['team'] for p in result['players']], [0, 0, 0, 1])
            opts['human_count'] = True
            with self.assertRaises(ValueError):
                build_lan_map(ds, opts)
        self.assertEqual(ds.maps, before)
