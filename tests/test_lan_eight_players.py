"""CPU-only eight-slot LAN contracts; real TCP loops have absolute bounds."""
from copy import deepcopy
import socket
import time
import unittest

import game.core  # Initialize core before importing the data singleton.
from game.core.skirmish import PLAYER_COLORS, SKIRMISH_MAP_IDS, build_skirmish_map
from game.data.store import DataStore
from game.net.lan import build_lan_map, default_lan_options


class MapContracts(unittest.TestCase):
    def test_defaults_cover_eight_choices_without_enabling_extra_players(self):
        options = default_lan_options()
        self.assertEqual((options['human_count'], options['ai_count']), (2, 0))
        self.assertEqual(options['colors'], list(PLAYER_COLORS))
        self.assertEqual(options['factions'], ['imperial'] * 8)
        self.assertNotIn('spawn_slots', options)
        options['colors'].reverse()
        self.assertEqual(default_lan_options()['colors'], list(PLAYER_COLORS))

    def test_all_eight_maps_and_every_capacity_valid_human_ai_mix(self):
        ds = DataStore.get()
        original = deepcopy(ds.maps)
        for mid in SKIRMISH_MAP_IDS:
            capacity = len(ds.maps[mid]['players'])
            for humans in range(2, capacity + 1):
                for ai in range(capacity - humans + 1):
                    for coop in (False, True):
                        with self.subTest(map=mid, humans=humans, ai=ai, cooperative=coop):
                            options = default_lan_options()
                            options.update(map_id=mid, human_count=humans, ai_count=ai, cooperative=coop)
                            result = build_lan_map(ds, options)
                            self.assertEqual(len(result['players']), humans + ai)
                            self.assertEqual([p['is_ai'] for p in result['players']], [False]*humans + [True]*ai)
                            self.assertEqual([p['team'] for p in result['players']],
                                             [0]*humans + [1]*ai if coop else list(range(humans + ai)))
                            shared = deepcopy(options)
                            shared.pop('human_count')
                            shared['teams'] = list(range(8))
                            shared['ai_count'] = humans + ai - 1
                            expected = build_skirmish_map(ds, shared)
                            for p, q in zip(result['players'], expected['players']):
                                for key in ('slot', 'start', 'start_units', 'color', 'faction'):
                                    self.assertEqual(p[key], q[key])
        self.assertEqual(ds.maps, original)

    def test_actual_map_capacity_and_malformed_counts_fail_closed(self):
        ds = DataStore.get()
        invalid = [(h, 0) for h in (True, False, None, '8', 8.0, -1, 0, 1, 9)]
        invalid += [(2, a) for a in (True, False, None, '6', 6.0, -1, 7, 9)]
        invalid += [(h, 9-h) for h in range(2, 9)]
        for h, a in invalid:
            with self.subTest(humans=h, ai=a), self.assertRaises(ValueError):
                build_lan_map(ds, dict(default_lan_options(), map_id='skirmish05', human_count=h, ai_count=a))
        for mid in SKIRMISH_MAP_IDS:
            capacity = len(ds.maps[mid]['players'])
            if capacity < 8:
                with self.subTest(map=mid), self.assertRaisesRegex(ValueError, 'capacity'):
                    build_lan_map(ds, dict(default_lan_options(), map_id=mid, human_count=capacity+1))

    def test_explicit_spawn_slots_preserve_canonical_slot_and_loadout(self):
        ds = DataStore.get()
        options = dict(default_lan_options(), map_id='skirmish05', human_count=8,
                       spawn_slots=list(reversed(range(8))))
        before = deepcopy(options)
        result = build_lan_map(ds, options)
        for slot, player in enumerate(result['players']):
            self.assertEqual(player['slot'], slot)
            self.assertEqual(player['start'], ds.maps['skirmish05']['players'][7-slot]['start'])
            self.assertEqual(player['start_units'], ds.maps['skirmish05']['players'][slot]['start_units'])
        self.assertEqual(options, before)
        for slots in ([0]*8, [True]+list(range(1, 8)), list(range(9)), list(range(7))):
            with self.subTest(slots=slots), self.assertRaises(ValueError):
                build_lan_map(ds, dict(options, spawn_slots=slots))


def free_port():
    with socket.socket() as sock:
        sock.bind(('127.0.0.1', 0))
        return sock.getsockname()[1]


class TcpContracts(unittest.TestCase):
    def pump(self, sessions, predicate, seconds=5):
        deadline = time.monotonic() + seconds
        while time.monotonic() < deadline:
            for session in sessions:
                session.poll()
                self.assertNotEqual(session.snapshot['status'], 'error', session.snapshot)
            if predicate():
                return
            time.sleep(.001)
        self.fail([s.snapshot for s in sessions])

    def lobby(self, recovery=False, humans=8, ai=0, map_id='skirmish05'):
        from game.net.lan import LanSession
        options = dict(default_lan_options(), map_id=map_id, human_count=humans, ai_count=ai,
                       spawn_slots=list(reversed(range(humans + ai))))
        host = LanSession.host(free_port(), options, recovery=recovery)
        self.addCleanup(host.close)
        sessions = [host]
        # A full burst of seven joins must fit the bounded admission pool.
        for slot in range(1, humans):
            client = LanSession.join('127.0.0.1', host.port, name=f'Human {slot}', recovery=recovery)
            self.addCleanup(client.close)
            sessions.append(client)
        self.pump(sessions, lambda: all(len(s.snapshot['players']) == humans for s in sessions))
        self.assertEqual(sorted(s.local_player for s in sessions), list(range(humans)))
        return sessions

    def launch_match(self, sessions):
        host = sessions[0]
        for session in sessions:
            session.set_ready(True)
        self.pump(sessions, lambda: host.snapshot['can_start'])
        host.start()
        self.pump(sessions, lambda: all(s.launch is not None for s in sessions))
        for session in sessions:
            self.assertEqual(session.launch['local_player'], session.local_player)
            self.assertEqual(session.launch['map_def'], host.launch['map_def'])
        from game.core.manager import GameManager
        managers = [GameManager.start_skirmish(s.launch['map_def']) for s in sessions]
        for session, manager in zip(sessions, managers):
            manager.state._net_session = session
        return managers

    def align(self, sessions, managers, target):
        from game.net.lan import FIXED_DT, precise_checksum
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline and any(m.state.tick < target for m in managers):
            for session, manager in zip(sessions, managers):
                if manager.state.tick < target:
                    session.advance(manager, FIXED_DT)
                else:
                    session.poll()
                self.assertNotEqual(session.snapshot['status'], 'error', session.snapshot)
        self.assertEqual([m.state.tick for m in managers], [target]*8)
        self.assertEqual(len({precise_checksum(m) for m in managers}), 1)

    def test_all_eight_maps_and_maximum_ai_mixes_launch_canonically(self):
        cases = [(mid, 2, 0) for mid in SKIRMISH_MAP_IDS]
        cases += [('skirmish05', 2, 6), ('skirmish05', 7, 1)]
        for mid, humans, ai in cases:
            with self.subTest(map=mid, humans=humans, ai=ai):
                sessions = self.lobby(humans=humans, ai=ai, map_id=mid)
                managers = self.launch_match(sessions)
                self.assertEqual(len(managers[0].state.players), humans + ai)
                self.assertEqual(sum(p.is_ai for p in managers[0].state.players.values()), ai)
                for session in sessions:
                    session.close()

    def test_slot_seven_cannot_spoof_another_owner_or_exceed_command_limit(self):
        from game.net.lan import MAX_COMMANDS, _commands
        for commands in ([dict(type='stop', player=6)],
                         [dict(type='stop', player=True)],
                         [dict(type='stop', player=7)]*(MAX_COMMANDS+1)):
            with self.subTest(commands=commands), self.assertRaises(ValueError):
                _commands(commands, 7)
        sessions = self.lobby()
        self.launch_match(sessions)
        high = next(s for s in sessions if s.local_player == 7)
        high._peers[0].send(dict(type='input', tick=0, checksum='a'*64,
                                 commands=[dict(type='stop', player=6)]))
        deadline = time.monotonic() + 3
        while sessions[0].snapshot['status'] != 'error' and time.monotonic() < deadline:
            high.poll()
            sessions[0].poll()
        self.assertEqual(sessions[0].snapshot['status'], 'error')
        self.assertIn('ownership', sessions[0].snapshot['error'])

    def test_welcome_accepts_slot_seven_and_rejects_invalid_slots(self):
        from game.net.lan import LanSession, GAME_VERSION, PROTOCOL_VERSION
        for slot in (7, True, False, '7', 7.0, -1, 0, 8, 9):
            with self.subTest(slot=slot):
                client = LanSession.join('127.0.0.1', free_port())
                self.addCleanup(client.close)
                message = dict(type='welcome', slot=slot, version=GAME_VERSION,
                               protocol=PROTOCOL_VERSION, content=client._content,
                               balance=client.station_balance)
                if type(slot) is int and slot == 7:
                    client._receive(client._peers[0], message)
                    self.assertEqual(client.local_player, 7)
                else:
                    with self.assertRaisesRegex(ValueError, 'Invalid slot'):
                        client._receive(client._peers[0], message)

    def test_eight_human_tcp_revision_readiness_launch_and_slot_seven_move(self):
        from game.core.commands import MoveCommand
        from game.net.lan import INPUT_DELAY
        sessions = self.lobby()
        host = sessions[0]
        with self.assertRaises(ValueError):
            host.start()
        for session in sessions:
            session.set_ready(True)
        self.pump(sessions, lambda: host.snapshot['can_start'])
        # Old in-flight consent cannot approve a revised eight-player map.
        sessions[-1].set_ready(True)
        options = host.snapshot['options']
        options['ai_difficulty'] = 'hard'
        host.configure(options)
        self.pump(sessions, lambda: all(s.snapshot['revision'] == 1 for s in sessions))
        self.assertFalse(host.snapshot['can_start'])
        self.assertFalse(any(p['ready'] for p in host.snapshot['players']))
        with self.assertRaises(ValueError):
            sessions[-1].configure(options)
        managers = self.launch_match(sessions)
        for slot, player in enumerate(host.launch['map_def']['players']):
            self.assertEqual(player['start'], DataStore.get().maps['skirmish05']['players'][7-slot]['start'])
        index = next(i for i, s in enumerate(sessions) if s.local_player == 7)
        manager = managers[index]
        ship = next(e for e in manager.state.entities.values() if e.owner == 7 and e.is_ship and not e.is_squadron)
        initial = (ship.pos.x, ship.pos.z)
        observed = [[] for _ in sessions]
        for i, gm in enumerate(managers):
            original = gm.step
            def record(dt, original=original, gm=gm, i=i):
                observed[i].extend((gm.state.tick, c.to_dict()) for c in gm.state.command_queue if c.player == 7)
                original(dt)
            gm.step = record
        from game.core import detmath
        from game.core.vectors import Vec3
        target = Vec3(ship.pos.x + detmath.sin(ship.yaw)*1000, 0,
                      ship.pos.z + detmath.cos(ship.yaw)*1000)
        manager.state.queue_command(MoveCommand(7, [ship.id], target))
        self.assertFalse(manager.state.command_queue)
        for target in range(1, INPUT_DELAY + 8):
            self.align(sessions, managers, target)
        self.assertNotEqual((ship.pos.x, ship.pos.z), initial)
        for commands in observed:
            self.assertEqual(len(commands), 1)
            self.assertEqual(commands[0][0], INPUT_DELAY)
            self.assertEqual(commands[0][1]['player'], 7)
            self.assertEqual(commands, observed[0])

    def test_eight_human_production_slot_seven_recovery_drains_and_waits_for_ack(self):
        from game.net.lan import FIXED_DT, precise_checksum
        sessions = self.lobby(recovery=True)
        managers = self.launch_match(sessions)
        self.align(sessions, managers, 4)
        index = next(i for i, s in enumerate(sessions) if s.local_player == 7)
        high = sessions[index]
        stale = deepcopy(high._recovery.credential)
        # Exercise a real released-frame drain: the original slot 7 is one tick
        # ahead, never silently rewound to the host's graph.
        deadline = time.monotonic() + 3
        while managers[index].state.tick == 4 and time.monotonic() < deadline:
            high.advance(managers[index], FIXED_DT)
            for session in sessions:
                session.poll()
        self.assertEqual(managers[index].state.tick, 5)
        high._peers[0].sock.shutdown(socket.SHUT_RDWR)
        high.poll()
        high._recovery.retry_at = float('inf')
        continuing = [s for s in sessions if s is not high]
        self.pump(continuing, lambda: sessions[0].snapshot['status'] == 'recovering')
        # Incomplete outsiders fill admission, not any reserved human slot.
        # The authenticated retry must rotate this bounded pool, never starve.
        import struct
        for _ in range(8):
            outsider = socket.create_connection(('127.0.0.1', sessions[0].port), timeout=1.)
            self.addCleanup(outsider.close)
            outsider.sendall(struct.pack('!I', 10000) + b'{')
            sessions[0].poll()
        self.pump(continuing, lambda: len([p for p in sessions[0]._peers if p.slot is None]) == 8)
        self.assertEqual(len([p for p in sessions[0]._peers if p.slot is not None]), 6)
        high._recovery.retry_at = 0.
        installed = set()
        withheld = None
        deadline = time.monotonic() + 8
        while time.monotonic() < deadline:
            for i, session in enumerate(sessions):
                session.poll()
                self.assertNotEqual(session.snapshot['status'], 'error', session.snapshot)
                if session.snapshot['status'] == 'recovering':
                    old_tick = managers[i].state.tick
                    self.assertFalse(session.advance(managers[i], 600.))
                    self.assertEqual(managers[i].state.tick, old_tick)
                    session.recovery_step(managers[i])
                    self.assertIn(managers[i].state.tick - old_tick, (0, 1))
                    candidate = session.take_restored_manager()
                    if candidate is not None:
                        managers[i] = candidate
                        candidate.state._net_session = session
                        installed.add(i)
                        if i == index:
                            withheld = candidate
                        else:
                            session.acknowledge_install(candidate)
            if len(installed) == 8:
                break
        self.assertEqual(installed, set(range(8)), [s.recovery_snapshot for s in sessions])
        self.assertIsNotNone(withheld)
        for _ in range(10):
            for session, manager in zip(sessions, managers):
                session.poll()
                self.assertFalse(session.advance(manager, 600.))
        self.assertEqual([s.snapshot['status'] for s in sessions], ['recovering']*8)
        self.assertEqual([m.state.tick for m in managers], [5]*8)
        self.assertEqual(len({precise_checksum(m) for m in managers}), 1)
        self.assertEqual(high.local_player, 7)
        high.acknowledge_install(withheld)
        self.pump(sessions, lambda: all(s.snapshot['status'] == 'running' for s in sessions))
        self.assertNotEqual(high._recovery.credential, stale)
        for target in range(6, 9):
            self.align(sessions, managers, target)


class RecoveryContracts(unittest.TestCase):
    def test_eight_human_original_slot_seven_credentials_and_all_peer_ack(self):
        from game.net.reconnect import RecoveryBarrier
        barrier = RecoveryBarrier(8, 'c'*64)
        credential = barrier.credentials(7)
        barrier.interrupt(7, tick=12, digest='d'*64, now=100.)
        deadline = barrier.deadline
        barrier.interrupt(7, tick=12, digest='d'*64, now=120.)
        self.assertEqual(barrier.deadline, deadline)
        with self.assertRaises(ValueError):
            barrier.authenticate(6, **credential, content='c'*64, now=121.)
        barrier.authenticate(7, **credential, content='c'*64, now=122.)
        for slot in range(7):
            barrier.acknowledge(slot, epoch=barrier.epoch, tick=12, digest='d'*64, now=123.)
        self.assertFalse(barrier.can_resume)
        with self.assertRaisesRegex(ValueError, 'All-peer'):
            barrier.finish(now=123.)
        barrier.acknowledge(7, epoch=barrier.epoch, tick=12, digest='d'*64, now=124.)
        self.assertTrue(barrier.can_resume)
        barrier.finish(now=125.)
        self.assertEqual(barrier.status, 'running')
        self.assertNotEqual(barrier.credentials(7), credential)
        barrier.interrupt(7, tick=13, digest='e'*64, now=130.)
        with self.assertRaises(ValueError):
            barrier.authenticate(7, **credential, content='c'*64, now=131.)
        barrier.poll(now=190.)
        self.assertEqual(barrier.status, 'error')
        self.assertIn('grace expired', barrier.error)

    def test_eight_human_pending_slot_seven_retry_restore_and_spend(self):
        from game.net.reconnect import PendingInputs
        ledger = PendingInputs(8, barrier_tick=12)
        commands = [dict(type='move', player=7, unit_ids=[76], target_pos=[10, 0, 20])]
        self.assertTrue(ledger.accept(7, sequence=0, target_tick=15, commands=commands))
        self.assertFalse(ledger.accept(7, sequence=0, target_tick=15, commands=commands))
        with self.assertRaises(ValueError):
            ledger.accept(6, sequence=0, target_tick=15, commands=commands)
        restored = PendingInputs.restore(ledger.export())
        self.assertEqual(restored.for_tick(15), commands)
        self.assertEqual(restored.export(), ledger.export())
        restored.commit_through(15)
        self.assertEqual(restored.for_tick(15), [])
        with self.assertRaises(ValueError):
            restored.accept(7, sequence=0, target_tick=16, commands=commands)
        self.assertEqual(PendingInputs.restore(restored.export()).export(), restored.export())

    def test_recovery_counts_remain_strict_and_above_eight_is_invalid(self):
        from game.net.reconnect import RecoveryBarrier, PendingInputs
        for count in (True, False, None, '8', 8.0, -1, 0, 1, 9):
            with self.subTest(count=count):
                with self.assertRaises(ValueError):
                    RecoveryBarrier(count, 'c'*64)
                with self.assertRaises(ValueError):
                    PendingInputs(count, barrier_tick=0)


if __name__ == '__main__':
    unittest.main()
