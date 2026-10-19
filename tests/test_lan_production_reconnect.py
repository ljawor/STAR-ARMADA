"""Production entrypoint tests: real TCP, real managers, opt-in backend."""
import socket
import time
import unittest
from game.net.lan import LanSession, default_lan_options, FIXED_DT, precise_checksum
from game.core.manager import GameManager
from test_lan import free_port, pump


class ProductionReconnectTests(unittest.TestCase):
    def setup_match(self, humans=3, clock=None):
        options = default_lan_options()
        options.update(human_count=humans, ai_count=min(1, 4-humans), map_id='skirmish04')
        host = LanSession.host(free_port(), options)
        host.enable_recovery(clock=clock)
        sessions = [host]
        self.addCleanup(host.close)
        for _ in range(humans-1):
            client = LanSession.join('127.0.0.1', host.port)
            client.enable_recovery(clock=clock)
            sessions.append(client)
            self.addCleanup(client.close)
        pump(sessions, lambda: all(len(s.snapshot['players']) == humans for s in sessions))
        for session in sessions:
            session.set_ready(True)
        pump(sessions, lambda: host.snapshot['can_start'])
        host.start()
        pump(sessions, lambda: all(s.launch for s in sessions))
        managers = [GameManager.start_skirmish(s.launch['map_def']) for s in sessions]
        for session, manager in zip(sessions, managers):
            manager.state._net_session = session
        return sessions, managers

    def align(self, sessions, managers, target):
        end = time.monotonic()+5
        while time.monotonic() < end and any(m.state.tick < target for m in managers):
            for s, m in zip(sessions, managers):
                if m.state.tick < target:
                    s.advance(m, FIXED_DT)
                else:
                    s.poll()
        self.assertEqual([m.state.tick for m in managers], [target]*len(managers), [s.snapshot for s in sessions])
        self.assertEqual(len({precise_checksum(m) for m in managers}), 1)

    def recover(self, sessions, managers):
        end = time.monotonic()+5
        installed = set()
        while time.monotonic() < end:
            for index, (session, manager) in enumerate(zip(sessions, managers)):
                session.poll()
                self.assertNotEqual(session.snapshot['status'], 'error', session.snapshot)
                if session.snapshot['status'] == 'recovering':
                    before = manager.state.tick
                    self.assertFalse(session.advance(manager, 600.0))
                    self.assertEqual(manager.state.tick, before)
                    session.recovery_step(manager)
                    self.assertIn(manager.state.tick-before, (0, 1))
                    restored = session.take_restored_manager()
                    if restored is not None:
                        managers[index] = restored
                        restored.state._net_session = session
                        session.acknowledge_install(restored)
                        installed.add(index)
            if len(installed) == len(sessions) and all(s.snapshot['status'] == 'running' for s in sessions):
                return
        self.fail([s.recovery_snapshot for s in sessions])

    def until_phase(self, sessions, managers, index, phase):
        end = time.monotonic()+5
        while time.monotonic() < end:
            for session, manager in zip(sessions, managers):
                session.poll()
                self.assertNotEqual(session.snapshot['status'], 'error', session.snapshot)
                session.recovery_step(manager)
                if sessions[index]._recovery.phase == phase:
                    return
        self.fail([s.recovery_snapshot for s in sessions])

    def until_installed(self, sessions, managers):
        """Wait until EVERY session holds its replacement graph.

        `until_phase` waits on one index, but a single driver loop polls the
        sessions in turn: the peer polled immediately after the host can still
        be one bundle frame behind the later-polled peers (the host writes one
        chunked frame per poll and delivers it asynchronously). That lag is a
        property of the driver's socket timing, not of the peers' ability to
        resume, so a one-index barrier can return while another consumed peer
        has not installed. The install-ACK correctness property needs all four
        graphs to exist, so wait for the whole set.
        """
        end = time.monotonic()+5
        while time.monotonic() < end:
            for session, manager in zip(sessions, managers):
                session.poll()
                self.assertNotEqual(session.snapshot['status'], 'error', session.snapshot)
                session.recovery_step(manager)
            if all(s._recovery.phase == 'install' for s in sessions):
                return
        self.fail([s.recovery_snapshot for s in sessions])

    def test_freeze_roundoff_never_exceeds_wire_grace_limit(self):
        # Windows monotonic readings near startup can make (now + 60) - now
        # round above 60 even when the clock has not advanced at all.
        now = [4.001]
        sessions, managers = self.setup_match(3, clock=lambda: now[0])
        self.align(sessions, managers, 8)
        sessions[1]._peers[0].sock.shutdown(socket.SHUT_RDWR)
        self.recover(sessions, managers)
        self.assertEqual(len({precise_checksum(m) for m in managers}), 1)
        self.align(sessions, managers, 10)

    def test_freeze_wire_bound_remains_strict_and_repeat_cannot_renew_grace(self):
        import math
        now = [4.001]
        sessions, _ = self.setup_match(2, clock=lambda: now[0])
        host, client = sessions
        host._recovery.begin()
        message = host._recovery.freeze_message()
        self.assertLessEqual(message['remaining'], 60.)
        client._recovery.receive(client._peers[0], message)
        deadline = client._recovery.deadline
        now[0] += 1.
        client._recovery.receive(client._peers[0], message)
        self.assertEqual(client._recovery.deadline, deadline)
        for remaining in (math.nextafter(60., math.inf), math.inf, math.nan, True, 0., -1.):
            with self.subTest(remaining=remaining):
                with self.assertRaisesRegex(ValueError, 'Invalid freeze deadline or epoch'):
                    client._recovery.receive(client._peers[0], dict(message, remaining=remaining))
        now[0] = deadline
        with self.assertRaisesRegex(ValueError, 'Reconnect grace expired'):
            client._recovery.check()

    def test_deadline_is_absolute_across_freeze_transfer_and_application_loading(self):
        for phase in ('freeze', 'transfer', 'install'):
            with self.subTest(phase=phase):
                now = [100.]
                sessions, managers = self.setup_match(3, clock=lambda: now[0])
                self.align(sessions, managers, 8)
                sessions[1]._peers[0].sock.shutdown(socket.SHUT_RDWR)
                if phase == 'freeze':
                    pump(sessions, lambda: all(s.snapshot['status'] == 'recovering' for s in sessions))
                else:
                    self.until_phase(sessions, managers, 1, phase)
                self.assertEqual([s._recovery.deadline for s in sessions], [160.]*3)
                now[0] = 159.999
                for s in sessions:
                    s.poll()
                    self.assertEqual(s.snapshot['status'], 'recovering')
                    self.assertEqual(s._recovery.deadline, 160.)
                now[0] = 160.
                for s in sessions:
                    s.poll()
                    self.assertEqual(s.snapshot['status'], 'error', s.snapshot)
                    self.assertIn('grace expired', s.snapshot['error'])
                for s in sessions:
                    s.close()

    def test_decode_time_is_part_of_absolute_grace(self):
        from unittest.mock import patch
        from game.net import live_recovery
        now = [100.]
        sessions, managers = self.setup_match(2, clock=lambda: now[0])
        self.align(sessions, managers, 8)
        sessions[1]._peers[0].sock.shutdown(socket.SHUT_RDWR)
        self.until_phase(sessions, managers, 1, 'transfer')
        original = live_recovery.restore_snapshot
        def slow_decode(data):
            manager = original(data)
            now[0] = 160.
            return manager
        with patch.object(live_recovery, 'restore_snapshot', slow_decode):
            pump(sessions, lambda: sessions[1].snapshot['status'] == 'error')
        self.assertIsNone(sessions[1].take_restored_manager())
        self.assertIn('grace expired', sessions[1].snapshot['error'])

    def test_no_peer_resumes_before_every_graph_and_bundle_install_ack(self):
        sessions, managers = self.setup_match(4)
        self.align(sessions, managers, 8)
        sessions[1]._peers[0].sock.shutdown(socket.SHUT_RDWR)
        self.until_installed(sessions, managers)
        for index in range(3):
            candidate = sessions[index].take_restored_manager()
            self.assertIsNotNone(candidate)
            managers[index] = candidate
            candidate.state._net_session = sessions[index]
            sessions[index].acknowledge_install(candidate)
        for _ in range(20):
            for s, gm in zip(sessions, managers):
                s.poll()
                self.assertFalse(s.advance(gm, 600))
                self.assertEqual(gm.state.tick, 8)
        self.assertEqual([s.snapshot['status'] for s in sessions], ['recovering']*4)
        last = sessions[3].take_restored_manager()
        self.assertIsNotNone(last)
        managers[3] = last
        last.state._net_session = sessions[3]
        sessions[3].acknowledge_install(last)
        pump(sessions, lambda: all(s.snapshot['status'] == 'running' for s in sessions))
        self.align(sessions, managers, 20)

    def test_invalid_and_rotated_credentials_cannot_replace_reserved_slot(self):
        from copy import deepcopy
        from game.net.lan import _Peer, GAME_VERSION, PROTOCOL_VERSION
        sessions, managers = self.setup_match(3)
        self.align(sessions, managers, 8)
        stale = deepcopy(sessions[1]._recovery.credential)
        sessions[1]._peers[0].sock.shutdown(socket.SHUT_RDWR)
        self.recover(sessions, managers)
        fresh = deepcopy(sessions[1]._recovery.credential)
        self.assertNotEqual(stale, fresh)
        self.align(sessions, managers, 10)
        sessions[1]._peers[0].sock.shutdown(socket.SHUT_RDWR)
        sessions[1].poll()
        sessions[1]._recovery.retry_at = float('inf')
        pump([sessions[0], sessions[2]], lambda: sessions[0].snapshot['status'] == 'recovering')
        invalid = deepcopy(fresh)
        invalid['token'] = '0'*64
        for credential in (stale, invalid):
            raw = socket.create_connection(('127.0.0.1', sessions[0].port))
            probe = _Peer(raw)
            self.addCleanup(probe.close)
            pump([sessions[0], sessions[2]], lambda: any(p.slot is None for p in sessions[0]._peers))
            probe.send(dict(type='recovery_auth', slot=1, version=GAME_VERSION, protocol=PROTOCOL_VERSION,
                            content=sessions[0]._content, **credential))
            probe.flush()
            pump([sessions[0], sessions[2]], lambda: not any(p.slot is None for p in sessions[0]._peers))
            self.assertEqual(sessions[0].snapshot['status'], 'recovering')
            self.assertEqual(len(sessions[0]._players), 3)
            probe.close()
        sessions[1]._recovery.retry_at = 0.
        self.recover(sessions, managers)
        self.align(sessions, managers, 25)

    def test_host_eof_retries_original_address_until_grace_without_migration(self):
        now = [100.]
        sessions, managers = self.setup_match(2, clock=lambda: now[0])
        self.align(sessions, managers, 8)
        host, client = sessions
        host._listener.close()
        host._listener = None
        for peer in host._peers:
            peer.close()
        host._peers = []
        pump([client], lambda: client.snapshot['status'] == 'recovering')
        original_address = client._recovery.address
        for value in (101., 130., 159.999):
            now[0] = value
            client.poll()
            self.assertEqual(client.snapshot['status'], 'recovering')
            self.assertEqual(client._recovery.deadline, 160.)
            self.assertEqual(client._recovery.address, original_address)
            self.assertFalse(client.advance(managers[1], 600))
        now[0] = 160.
        client.poll()
        self.assertEqual(client.snapshot['status'], 'error')
        self.assertIn('grace expired', client.snapshot['error'])

    def test_abort_is_terminal_and_notifies_continuing_participants(self):
        sessions, managers = self.setup_match(3)
        self.align(sessions, managers, 8)
        sessions[1]._peers[0].sock.shutdown(socket.SHUT_RDWR)
        pump(sessions, lambda: all(s.snapshot['status'] == 'recovering' for s in sessions))
        sessions[0].abort_recovery()
        self.assertEqual(sessions[0].snapshot['status'], 'error')
        pump([sessions[2]], lambda: sessions[2].snapshot['status'] == 'error')
        self.assertIn('explicit', sessions[2].snapshot['error'])

    def test_corrupt_real_transfer_is_fatal_not_retried(self):
        sessions, managers = self.setup_match(2)
        self.align(sessions, managers, 8)
        sessions[1]._peers[0].sock.shutdown(socket.SHUT_RDWR)
        self.until_phase(sessions, managers, 0, 'install')
        for sender in sessions[0]._recovery.senders.values():
            sender.data = sender.data[:-1] + bytes([sender.data[-1] ^ 1])
        pump(sessions, lambda: sessions[1].snapshot['status'] == 'error')
        self.assertIn('hash mismatch', sessions[1].snapshot['error'])

    def test_authenticated_graph_desync_is_fatal(self):
        sessions, managers = self.setup_match(3)
        self.align(sessions, managers, 8)
        managers[2].state.players[0].credits += 1
        sessions[1]._peers[0].sock.shutdown(socket.SHUT_RDWR)
        self.until_phase(sessions, managers, 0, 'drain')
        end = time.monotonic()+3
        while sessions[0].snapshot['status'] != 'error' and time.monotonic() < end:
            for s, gm in zip(sessions, managers):
                s.poll()
                s.recovery_step(gm)
        self.assertEqual(sessions[0].snapshot['status'], 'error')
        self.assertIn('desync', sessions[0].snapshot['error'].lower())

    def test_ack_rejects_bool_epoch_instead_of_accepting_int_equivalence(self):
        sessions, managers = self.setup_match(2)
        self.align(sessions, managers, 8)
        sessions[1]._peers[0].sock.shutdown(socket.SHUT_RDWR)
        self.until_phase(sessions, managers, 1, 'install')
        recovery = sessions[0]._recovery
        sessions[1]._peers[0].send(dict(type='recovery_ack', epoch=True, tick=recovery.target,
                                      graph=recovery.graph_digest, bundle=recovery.bundle_digest))
        pump(sessions, lambda: sessions[0].snapshot['status'] == 'error')

    def test_rotation_survives_eof_after_last_install_ack_before_resume_delivery(self):
        sessions, managers = self.setup_match(2)
        self.align(sessions, managers, 8)
        sessions[1]._peers[0].sock.shutdown(socket.SHUT_RDWR)
        self.until_phase(sessions, managers, 1, 'install')
        for index, session in enumerate(sessions):
            candidate = session.take_restored_manager()
            self.assertIsNotNone(candidate)
            managers[index] = candidate
            candidate.state._net_session = session
            session.acknowledge_install(candidate)
        sessions[1]._peers[0].flush()  # Deliver only the last install ACK.
        peer = next(p for p in sessions[0]._peers if p.slot == 1)
        from unittest.mock import patch
        with patch.object(peer, 'flush', lambda: None):
            pump([sessions[0]], lambda: sessions[0].snapshot['status'] == 'running')
            peer.sock.shutdown(socket.SHUT_RDWR)  # Queued private grant/resume is LOST.
        self.recover(sessions, managers)
        self.align(sessions, managers, 20)

    def test_second_loss_discards_queued_old_freeze_report_and_install_ack(self):
        for queued in ('freeze_report', 'install_ack'):
            with self.subTest(queued=queued):
                sessions, managers = self.setup_match(3)
                self.align(sessions, managers, 8)
                sessions[1]._peers[0].sock.shutdown(socket.SHUT_RDWR)
                if queued == 'freeze_report':
                    pump(sessions, lambda: sessions[1]._recovery.epoch == 1
                         and sessions[1]._recovery.phase == 'freeze')
                    sessions[1].recovery_step(managers[1])
                else:
                    self.until_phase(sessions, managers, 1, 'install')
                    candidate = sessions[1].take_restored_manager()
                    managers[1] = candidate
                    candidate.state._net_session = sessions[1]
                    sessions[1].acknowledge_install(candidate)
                sessions[2]._peers[0].sock.shutdown(socket.SHUT_RDWR)
                self.recover(sessions, managers)
                self.align(sessions, managers, 20)
                for s in sessions:
                    s.close()

    def test_second_interruption_restarts_work_without_renewing_grace(self):
        for phase in ('drain', 'transfer', 'install'):
            with self.subTest(phase=phase):
                now = [100.]
                sessions, managers = self.setup_match(3, clock=lambda: now[0])
                self.align(sessions, managers, 8)
                sessions[1]._peers[0].sock.shutdown(socket.SHUT_RDWR)
                self.until_phase(sessions, managers, 1, phase)
                now[0] = 120.
                sessions[2]._peers[0].sock.shutdown(socket.SHUT_RDWR)
                for s in sessions:
                    s.poll()
                    self.assertEqual(s._recovery.deadline, 160.)
                self.recover(sessions, managers)
                self.assertEqual(sessions[0]._recovery.epoch, 2)
                self.align(sessions, managers, 20)
                for s in sessions:
                    s.close()

    def test_install_ack_at_absolute_deadline_is_terminal(self):
        now = [100.]
        sessions, managers = self.setup_match(2, clock=lambda: now[0])
        self.align(sessions, managers, 8)
        sessions[1]._peers[0].sock.shutdown(socket.SHUT_RDWR)
        self.until_phase(sessions, managers, 0, 'install')
        candidate = sessions[0].take_restored_manager()
        now[0] = 160.
        with self.assertRaisesRegex(ValueError, 'grace expired'):
            sessions[0].acknowledge_install(candidate)
        self.assertEqual(sessions[0].snapshot['status'], 'error')

    def test_recovery_cannot_be_enabled_after_a_handshake(self):
        from test_lan import SimulationTests
        host, client = SimulationTests().sessions(launch=False)
        self.addCleanup(host.close)
        self.addCleanup(client.close)
        for session in (host, client):
            with self.assertRaisesRegex(ValueError, 'handshake'):
                session.enable_recovery()

    def test_large_unspent_report_uses_chunks_without_raising_frame_limits(self):
        from game.core.commands import StopCommand
        from game.net.lan import MAX_FRAME, MAX_BUFFER
        sessions, managers = self.setup_match(2)
        self.align(sessions, managers, 6)
        for tick in (6, 7):
            for _ in range(64):
                managers[1].state.queue_command(StopCommand(1, tuple(range(2147483392, 2147483648))))
            self.align(sessions, managers, tick+1)
        sessions[1]._peers[0].sock.shutdown(socket.SHUT_RDWR)
        self.recover(sessions, managers)
        self.assertEqual(MAX_FRAME, 262144)
        self.assertEqual(MAX_BUFFER, 524288)
        self.align(sessions, managers, 20)

    def test_normal_ticks_have_bounded_history_and_never_capture_graph_snapshots(self):
        from unittest.mock import patch
        from game.net import live_recovery
        sessions, managers = self.setup_match(4)
        with patch.object(live_recovery, 'capture_snapshot', side_effect=AssertionError('normal tick snapshot')):
            self.align(sessions, managers, 100)
        for s in sessions:
            self.assertLessEqual(len(s._recovery.local), 12)
            self.assertLessEqual(len(s._recovery.history), 12)

    def test_drain_runs_real_recorder_hooks_and_paid_action_is_recorded_once(self):
        from game.core.commands import BuildStationCommand
        from game.core.vectors import Vec3
        from game.net.replay import MatchRecording
        sessions, managers = self.setup_match(2)
        self.align(sessions, managers, 5)
        gm = managers[1]
        builder = next(e for e in gm.state.entities.values() if e.owner == 1 and e.is_construction
                       and 'research_station' in gm.ds.ships[e.data_id].can_build_stations)
        gm.state.queue_command(BuildStationCommand(1, builder.id, 'research_station', builder.pos+Vec3(600, 0, 0)))
        self.align(sessions, managers, 6)
        recorder = MatchRecording(gm, mode='lan')
        self.addCleanup(recorder.close)
        end = time.monotonic()+2
        while managers[0].state.tick < 9 and time.monotonic() < end:
            sessions[0].advance(managers[0], FIXED_DT)
            sessions[1].poll()
        self.assertEqual([m.state.tick for m in managers], [9, 6])
        sessions[1]._peers[0].sock.shutdown(socket.SHUT_RDWR)
        self.until_phase(sessions, managers, 1, 'install')
        commands = recorder.to_dict()['commands']
        self.assertEqual([(c['tick'], c['cmd']['type']) for c in commands], [(8, 'build_station')])
        self.assertEqual(recorder.to_dict()['end_tick'], 9)
        for index, session in enumerate(sessions):
            candidate = session.take_restored_manager()
            self.assertIsNotNone(candidate)
            if index == 1:
                recorder.rebind_manager(candidate)
            managers[index] = candidate
            candidate.state._net_session = session
            session.acknowledge_install(candidate)
        pump(sessions, lambda: all(s.snapshot['status'] == 'running' for s in sessions))
        self.align(sessions, managers, 20)
        self.assertEqual(recorder.to_dict()['commands'], commands)
        self.assertEqual(recorder.to_dict()['end_tick'], 20)
        self.assertEqual(len(managers[1].state.entities[builder.id].build_queue), 1)

    def test_maximal_valid_unspent_journal_uses_chunk_backpressure(self):
        from game.core.commands import StopCommand
        sessions, managers = self.setup_match(2)
        self.align(sessions, managers, 6)
        units = tuple(range(2147483392, 2147483648))
        for tick in (6, 7):
            for _ in range(64):
                managers[1].state.queue_command(StopCommand(1, units))
            self.align(sessions, managers, tick+1)
        end = time.monotonic()+2
        while managers[0].state.tick < 11 and time.monotonic() < end:
            sessions[0].advance(managers[0], FIXED_DT)
            sessions[1].poll()
        self.assertEqual([m.state.tick for m in managers], [11, 8])
        sessions[1]._peers[0].sock.shutdown(socket.SHUT_RDWR)
        self.recover(sessions, managers)
        self.align(sessions, managers, 20)

    def test_startup_skew_uses_authoritative_empty_released_frames(self):
        sessions, managers = self.setup_match(2)
        self.assertFalse(sessions[1].advance(managers[1], FIXED_DT))
        end = time.monotonic()+2
        while managers[0].state.tick < 2 and time.monotonic() < end:
            sessions[0].advance(managers[0], FIXED_DT)
            sessions[1].poll()
        self.assertEqual([m.state.tick for m in managers], [2, 0])
        sessions[1]._peers[0].sock.shutdown(socket.SHUT_RDWR)
        self.recover(sessions, managers)
        self.align(sessions, managers, 15)

    def test_disconnect_during_initial_loading_recovers_without_tick_zero_duplication(self):
        for tick in (0, 1, 2):
            with self.subTest(tick=tick):
                sessions, managers = self.setup_match(2)
                if tick:
                    self.align(sessions, managers, tick)
                sessions[1]._peers[0].sock.shutdown(socket.SHUT_RDWR)
                self.recover(sessions, managers)
                self.align(sessions, managers, 10)
                for session in sessions:
                    session.close()

    def test_missing_checksum_is_legal_only_for_empty_startup_frames(self):
        sessions, managers = self.setup_match(2)
        recovery = sessions[0]._recovery
        for tick, commands in ((8, []), (1, [{'type': 'stop', 'player': 0, 'unit_ids': [1]}])):
            with self.subTest(tick=tick):
                with self.assertRaisesRegex(ValueError, 'startup|checksum'):
                    recovery.validate_frame(dict(type='frame', tick=tick, commands=commands, checksum=None))

    def test_restored_journal_rejects_spent_and_unsealed_future_identities(self):
        from copy import deepcopy
        from game.net.lan import _json
        sessions, managers = self.setup_match(2)
        self.align(sessions, managers, 8)
        sessions[1]._peers[0].sock.shutdown(socket.SHUT_RDWR)
        self.recover(sessions, managers)
        recovery = sessions[0]._recovery
        for target in (recovery.target-1, recovery.target+3):
            with self.subTest(target=target):
                bundle = deepcopy(recovery.bundle)
                report = bundle['reports'][0]
                report['batches'].append(dict(type='input', tick=target, commands=[], checksum=report['checksum']))
                report['batches'].sort(key=lambda x: x['tick'])
                with self.assertRaisesRegex(ValueError, 'journal'):
                    recovery.install_bundle(_json(bundle))

    def test_restore_rejects_future_frame_that_disagrees_with_input_journal(self):
        import json
        from copy import deepcopy
        from game.net.lan import _json
        sessions, managers = self.setup_match(2)
        self.align(sessions, managers, 8)
        sessions[1]._peers[0].sock.shutdown(socket.SHUT_RDWR)
        self.recover(sessions, managers)
        recovery = sessions[0]._recovery
        bundle = deepcopy(recovery.bundle)
        bundle['frames'][0]['commands'] = [{'type': 'stop', 'player': 0, 'unit_ids': [1]}]
        with self.assertRaisesRegex(ValueError, 'journal'):
            recovery.install_bundle(_json(bundle))

    def test_skewed_paid_batches_preserve_original_target_and_exact_future(self):
        from game.core.commands import BuildStationCommand
        from game.core.vectors import Vec3
        from game.net.reconnect import capture_snapshot, restore_snapshot
        for humans in (2, 3, 4):
            for mode in ('pending', 'lost_before_accept', 'accepted_unspent', 'spent'):
                with self.subTest(humans=humans, mode=mode):
                    sessions, managers = self.setup_match(humans)
                    self.align(sessions, managers, 8)
                    control = restore_snapshot(capture_snapshot(managers[0]))
                    commands = []
                    for slot in range(humans):
                        gm = managers[slot]
                        builder = next(e for e in gm.state.entities.values() if e.owner == slot
                                       and e.is_construction and 'research_station' in
                                       gm.ds.ships[e.data_id].can_build_stations)
                        cmd = BuildStationCommand(slot, builder.id, 'research_station', builder.pos + Vec3(600, 0, 0))
                        commands.append(cmd)
                        gm.state.queue_command(cmd)
                    lost = sessions[1]
                    if mode == 'lost_before_accept':
                        from unittest.mock import patch
                        gate = patch.object(lost._peers[0], 'flush', lambda: None)
                        gate.start()
                        self.addCleanup(gate.stop)
                        lost.advance(managers[1], FIXED_DT)
                        self.assertNotIn(1, sessions[0]._inputs.get(11, {}))
                    elif mode == 'accepted_unspent':
                        lost.advance(managers[1], FIXED_DT)
                        pump(sessions, lambda: 1 in sessions[0]._inputs.get(11, {}))
                    elif mode == 'spent':
                        self.align(sessions, managers, 12)
                    # Keep a continuing host up to two released ticks ahead.
                    start = max(m.state.tick for m in managers)
                    end = time.monotonic()+2
                    while managers[0].state.tick < start+2 and time.monotonic() < end:
                        sessions[0].advance(managers[0], FIXED_DT)
                        for s in sessions[1:]:
                            s.poll()
                    self.assertGreater(managers[0].state.tick, min(m.state.tick for m in managers))
                    if mode == 'lost_before_accept':
                        self.assertNotIn(1, sessions[0]._inputs.get(11, {}))
                    lost._peers[0].sock.shutdown(socket.SHUT_RDWR)
                    if mode == 'lost_before_accept':
                        gate.stop()
                    self.recover(sessions, managers)
                    self.assertEqual(len({m.state.tick for m in managers}), 1)
                    for future_tick in range(managers[0].state.tick, 41):
                        while control.state.tick < future_tick:
                            if control.state.tick == 11:
                                control.state.command_queue.extend(commands)
                            control.step(FIXED_DT)
                        self.align(sessions, managers, future_tick)
                        self.assertEqual({precise_checksum(m) for m in managers},
                                         {precise_checksum(control)}, future_tick)
                    for cmd in commands:
                        for gm in managers:
                            queue = gm.state.entities[cmd.unit_ids[0]].build_queue
                            self.assertEqual(len(queue), 1)
                    for session in sessions:
                        session.close()

    def test_explicit_close_is_terminal_not_an_unexpected_eof_retry(self):
        sessions, managers = self.setup_match(2)
        self.align(sessions, managers, 8)
        sessions[1].close()
        pump([sessions[0]], lambda: sessions[0].snapshot['status'] == 'error')
        self.assertIn('explicit', sessions[0].snapshot['error'].lower())

    def test_client_cannot_opt_in_after_hello_was_sent_before_welcome(self):
        host = LanSession.host(free_port(), default_lan_options())
        self.addCleanup(host.close)
        client = LanSession.join('127.0.0.1', host.port)
        self.addCleanup(client.close)
        pump([client], lambda: not client._peers[0].tx)
        self.assertEqual(client.local_player, -1)
        with self.assertRaisesRegex(ValueError, 'handshake'):
            client.enable_recovery()

    def test_mixed_optin_is_rejected_before_slot_admission(self):
        for host_optin in (False, True):
            with self.subTest(host_optin=host_optin):
                host = LanSession.host(free_port(), default_lan_options(), recovery=host_optin)
                self.addCleanup(host.close)
                client = LanSession.join('127.0.0.1', host.port, recovery=not host_optin)
                self.addCleanup(client.close)
                pump([host, client], lambda: client.snapshot['status'] == 'error')
                self.assertEqual(len(host._players), 1)
                self.assertEqual(host.snapshot['status'], 'lobby')
                host.close()
                client.close()

    def test_host_join_recovery_optin_is_applied_before_hello(self):
        host = LanSession.host(free_port(), default_lan_options(), recovery=True)
        self.addCleanup(host.close)
        client = LanSession.join('127.0.0.1', host.port, recovery=True)
        self.addCleanup(client.close)
        pump([host, client], lambda: client._recovery.credential is not None)
        self.assertEqual(client.local_player, 1)

    def test_clock_can_be_supplied_before_handshake(self):
        host = LanSession.host(free_port(), default_lan_options())
        self.addCleanup(host.close)
        now = [100.]
        host.enable_recovery(clock=lambda: now[0])
        self.assertEqual(host._recovery.clock(), 100.)

    def test_joined_loss_retains_continuing_socket_and_resumes_exact_graph(self):
        sessions, managers = self.setup_match(3)
        self.align(sessions, managers, 12)
        host, lost, continuing = sessions
        retained = next(p for p in host._peers if p.slot == 2)
        old_ticks = [m.state.tick for m in managers]
        lost._peers[0].sock.shutdown(socket.SHUT_RDWR)
        self.recover(sessions, managers)
        self.assertIs(next(p for p in host._peers if p.slot == 2), retained)
        self.assertIsNotNone(host._listener)
        self.assertEqual([m.state.tick for m in managers], old_ticks)
        self.align(sessions, managers, 42)
        self.assertNotIn('token', repr([s.snapshot for s in sessions]))
        self.assertNotIn('token', repr([s.recovery_snapshot for s in sessions]))
