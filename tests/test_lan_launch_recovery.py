"""Launch loss exercises lobby-to-graph recovery over real TCP."""
import socket
import multiprocessing
from types import SimpleNamespace
import os
import time
import unittest
from unittest.mock import patch
from game.net.lan import LanSession, _Peer, default_lan_options, FIXED_DT, precise_checksum
from game.core.manager import GameManager
from test_lan import free_port, pump
import test_lan_production_reconnect as production


def isolated_client(port, pipe, prelaunch=False):
    """Spawned graph/transport owner; pipe carries no resume credentials."""
    session = LanSession.join('127.0.0.1', port, recovery=True)
    try:
        end = time.monotonic() + 15
        while time.monotonic() < end:
            session.poll()
            if session._recovery.credential and len(session.snapshot['players']) == 2:
                break
            time.sleep(.001)
        session.set_ready(True)
        session.poll()
        pipe.send(('ready', os.getpid()))
        if not pipe.poll(15) or pipe.recv() != 'go':
            raise RuntimeError('Parent launch coordination timed out')
        manager = None
        installed = False
        while time.monotonic() < end:
            session.poll()
            if session.snapshot['status'] == 'error':
                raise RuntimeError(session.snapshot['error'])
            if manager is None and session.launch:
                manager = GameManager.start_skirmish(session.launch['map_def'])
                manager.state._net_session = session
            if manager is not None:
                if session.snapshot['status'] == 'recovering':
                    session.recovery_step(manager)
                    candidate = session.take_restored_manager()
                    if candidate is not None:
                        manager = candidate
                        manager.state._net_session = session
                        session.acknowledge_install(manager)
                        installed = True
                elif manager.state.tick < 8:
                    session.advance(manager, FIXED_DT)
                if (installed or prelaunch) and manager.state.tick == 8:
                    pipe.send(('done', os.getpid(), manager.state.tick, precise_checksum(manager), session.local_player))
                    if not pipe.poll(15):
                        raise RuntimeError('Parent completion coordination timed out')
                    pipe.recv()
                    return
            time.sleep(.001)
        raise RuntimeError('Independent client recovery timed out')
    except Exception as exc:
        pipe.send(('error', str(exc)))
    finally:
        session.close()
        pipe.close()


class LaunchRecoveryTests(unittest.TestCase):
    align = production.ProductionReconnectTests.align
    recover = production.ProductionReconnectTests.recover

    def test_reverse_released_startup_skew_preserves_paid_targets_and_recording(self):
        from game.core.commands import BuildStationCommand, PlayerCommand
        from game.core.vectors import Vec3
        from game.net.reconnect import capture_snapshot, restore_snapshot
        from game.net.replay import MatchRecording
        for humans in (2, 3, 4):
            with self.subTest(humans=humans):
                sessions = self.lobby(humans)
                sessions[0].start()
                pump(sessions, lambda: all(s.launch for s in sessions))
                managers = [GameManager.start_skirmish(s.launch['map_def']) for s in sessions]
                control = restore_snapshot(capture_snapshot(managers[0]))
                recorders, commands = [], []
                for slot, (session, manager) in enumerate(zip(sessions, managers)):
                    manager.state._net_session = session
                    recorder = MatchRecording(manager, mode='lan')
                    recorders.append(recorder)
                    self.addCleanup(recorder.close)
                    builder = next(e for e in manager.state.entities.values() if e.owner == slot
                                   and e.is_construction and 'research_station' in
                                   manager.ds.ships[e.data_id].can_build_stations)
                    command = BuildStationCommand(slot, builder.id, 'research_station',
                                                  builder.pos + Vec3(600, 0, 0))
                    commands.append(command.to_dict())
                    manager.state.queue_command(command)
                # Seal every initial input without stepping the host. Releasing
                # frame zero is legitimate even while its graph remains at zero.
                for session, manager in zip(sessions, managers):
                    self.assertFalse(session.advance(manager, FIXED_DT))
                pump(sessions, lambda: 0 in sessions[1]._frames)
                self.assertTrue(sessions[1].advance(managers[1], FIXED_DT))
                self.assertEqual([m.state.tick for m in managers], [0, 1] + [0]*(humans-2))
                launch = sessions[1]._launch
                sessions[1]._peers[0].sock.shutdown(socket.SHUT_RDWR)
                # No recovery_launch may call start_skirmish for an existing
                # graph. The eventual snapshot install is a separate handoff.
                with patch.object(GameManager, 'start_skirmish', side_effect=AssertionError('duplicate launch graph')):
                    end = time.monotonic() + 5
                    installed = set()
                    while time.monotonic() < end:
                        for index, (session, manager) in enumerate(zip(sessions, managers)):
                            session.poll()
                            self.assertNotEqual(session.snapshot['status'], 'error', session.snapshot)
                            if session.snapshot['status'] == 'recovering':
                                session.recovery_step(manager)
                                candidate = session.take_restored_manager()
                                if candidate is not None:
                                    recorders[index].rebind_manager(candidate)
                                    managers[index] = candidate
                                    candidate.state._net_session = session
                                    session.acknowledge_install(candidate)
                                    installed.add(index)
                        if len(installed) == humans and all(s.snapshot['status'] == 'running' for s in sessions):
                            break
                    self.assertEqual(installed, set(range(humans)), [s.recovery_snapshot for s in sessions])
                self.assertIs(sessions[1]._launch, launch)
                for tick in range(1, 11):
                    self.align(sessions, managers, tick)
                    while control.state.tick < tick:
                        if control.state.tick == 3:
                            control.state.command_queue.extend(PlayerCommand.from_dict(c) for c in commands)
                        control.step(FIXED_DT)
                    self.assertEqual(precise_checksum(managers[0]), precise_checksum(control))
                for recorder in recorders:
                    paid = [(c['tick'], c['cmd']) for c in recorder.to_dict()['commands']
                            if c['cmd']['type'] == 'build_station']
                    self.assertEqual(paid, [(3, c) for c in commands])
                    from game.net.replay import PlaybackSession
                    playback = PlaybackSession(recorder.to_dict())
                    while not playback.ended:
                        playback.step()
                    self.assertEqual(precise_checksum(playback.gm), precise_checksum(control))
                for session in sessions:
                    session.close()

    def test_host_detects_ready_lobby_eof_before_start_and_resumes_original_slots(self):
        for humans in (2, 3, 4):
            with self.subTest(humans=humans):
                sessions = self.lobby(humans)
                host, client = sessions[:2]
                credential = dict(client._recovery.credential)
                client._peers[0].sock.shutdown(socket.SHUT_RDWR)
                pump([host], lambda: host.snapshot['status'] != 'lobby')  # Observe the real EOF before start/auth.
                self.assertEqual(host.snapshot['status'], 'recovering', host.snapshot)
                self.assertFalse(host.snapshot['can_start'])
                self.assertIsNone(host.launch)
                pump(sessions, lambda: all(s.snapshot['status'] == 'lobby' for s in sessions))
                self.assertTrue(host.snapshot['can_start'])
                self.assertEqual([s.local_player for s in sessions], list(range(humans)))
                self.assertNotEqual(client._recovery.credential['token'], credential['token'])
                self.assertTrue(all(s.launch is None for s in sessions))
                host.start()
                pump(sessions, lambda: all(s.launch for s in sessions))
                managers = [GameManager.start_skirmish(s.launch['map_def']) for s in sessions]
                self.align(sessions, managers, 8)
                for session in sessions:
                    session.close()

    def test_recovered_lobby_revokes_unseen_configuration_consent(self):
        for humans in (2, 3, 4):
            with self.subTest(humans=humans):
                sessions = self.lobby(humans)
                host, client = sessions[:2]
                old_revision = client._revision
                options = host.snapshot['options']
                options['cooperative'] = True
                host.configure(options)  # This lobby never reaches the lost client.
                client._peers[0].sock.shutdown(socket.SHUT_RDWR)
                pump([host], lambda: host.snapshot['status'] == 'recovering')
                with self.assertRaises(ValueError):
                    host.configure(options)
                with self.assertRaises(ValueError):
                    host.start()
                pump(sessions, lambda: all(s.snapshot['status'] == 'lobby' for s in sessions))
                self.assertEqual(client._revision, old_revision + 1)
                self.assertEqual(client.snapshot['options'], options)
                self.assertFalse(client._ready_requested)
                self.assertFalse(any(p['ready'] for p in host.snapshot['players']))
                client._peers[0].send(dict(type='ready', ready=True, revision=old_revision))
                for _ in range(10):
                    for session in sessions:
                        session.poll()
                self.assertFalse(host.snapshot['players'][1]['ready'])
                self.assertFalse(host.snapshot['can_start'])
                for session in sessions:
                    session.set_ready(True)
                pump(sessions, lambda: host.snapshot['can_start'])
                host.start()
                pump(sessions, lambda: all(s.launch for s in sessions))
                managers = [GameManager.start_skirmish(s.launch['map_def']) for s in sessions]
                self.align(sessions, managers, 8)
                for session in sessions:
                    session.close()

    def test_start_races_final_lobby_resume_without_building_a_recovery_graph(self):
        for humans in (2, 3, 4):
            with self.subTest(humans=humans):
                sessions = self.lobby(humans)
                host, client = sessions[:2]
                client._peers[0].sock.shutdown(socket.SHUT_RDWR)
                pump([host], lambda: host.snapshot['status'] == 'recovering')
                pump(sessions, lambda: all(s._recovery.phase == 'lobby_install' for s in sessions))
                # All clients have flushed ACKs, but have not consumed resume.
                pump([host], lambda: host.snapshot['status'] == 'lobby')
                self.assertEqual(client.snapshot['status'], 'recovering')
                self.assertIsNone(client.launch)
                host.start()
                pump(sessions, lambda: all(s.launch for s in sessions))
                self.assertTrue(all(s.snapshot['status'] == 'running' for s in sessions))
                managers = [GameManager.start_skirmish(s.launch['map_def']) for s in sessions]
                self.align(sessions, managers, 8)
                for session in sessions:
                    session.close()

    def test_lobby_install_retry_uses_staged_bearer_and_original_grace(self):
        for humans in (2, 3, 4):
            with self.subTest(humans=humans):
                sessions = self.lobby(humans)
                host, client = sessions[:2]
                now = [100.]
                for session in sessions:
                    session._recovery.clock = lambda: now[0]
                client._peers[0].sock.shutdown(socket.SHUT_RDWR)
                pump([host], lambda: host.snapshot['status'] == 'recovering')
                original = _Peer.flush
                def hold_ack(peer):
                    if peer.target is None or not peer.tx or b'recovery_lobby_ack' not in peer.tx:
                        original(peer)
                with patch.object(_Peer, 'flush', hold_ack):
                    pump(sessions, lambda: client._recovery.phase == 'lobby_install')
                    staged = dict(client._recovery.credential)
                    self.assertEqual(staged['generation'], 1)
                    self.assertEqual(host._recovery.generation, 0)
                    now[0] = 150.
                    client._peers[0].sock.shutdown(socket.SHUT_RDWR)
                    pump([host], lambda: host._recovery.epoch == 2)
                    self.assertEqual(host._recovery.deadline, 160.)
                    client._recovery.retry_at = 0.
                    pump(sessions, lambda: client._recovery.phase == 'lobby_install'
                         and client._recovery.epoch == 2)
                    self.assertEqual(client._recovery.credential, staged)
                    self.assertEqual(client._recovery.deadline, 160.)
                    now[0] = 160.
                    for session in sessions:
                        session.poll()
                    self.assertEqual(host.snapshot['status'], 'error')
                    self.assertIn('grace expired', host.snapshot['error'])
                    self.assertEqual(client.snapshot['status'], 'error')
                for session in sessions:
                    session.close()

    def test_withdrawn_ready_consent_survives_lost_write_and_frozen_lobby(self):
        for humans in (2, 3, 4):
            with self.subTest(humans=humans):
                sessions = self.lobby(humans)
                host, client = sessions[:2]
                client.set_ready(False)  # Queued but never flushed on the lost TCP socket.
                if humans > 2:
                    sessions[-1].set_ready(False)  # Still connected, arrives after freeze.
                client._peers[0].sock.shutdown(socket.SHUT_RDWR)
                pump([host], lambda: host.snapshot['status'] == 'recovering')
                pump(sessions, lambda: all(s.snapshot['status'] in ('lobby', 'error') for s in sessions))
                self.assertTrue(all(s.snapshot['status'] == 'lobby' for s in sessions), [s.snapshot for s in sessions])
                self.assertFalse(host.snapshot['players'][1]['ready'])
                if humans > 2:
                    self.assertFalse(host.snapshot['players'][-1]['ready'])
                self.assertFalse(host.snapshot['can_start'])
                for session in sessions:
                    session.close()

    def test_recovery_launch_keeps_map_validation_and_unlaunched_tick_zero_guard(self):
        from copy import deepcopy
        sessions = self.lobby(2)
        host, client = sessions
        host.start()
        pump(sessions, lambda: all(s.launch for s in sessions))
        managers = [GameManager.start_skirmish(s.launch['map_def']) for s in sessions]
        self.align(sessions, managers, 1)
        client._recovery.begin()
        message = dict(type='recovery_launch', map_def=deepcopy(host.launch['map_def']),
                       players=host.snapshot['players'], options=host.snapshot['options'],
                       revision=host.snapshot['revision'])
        launch = client._launch
        client._receive(client._peers[0], message)
        self.assertIs(client._launch, launch)
        self.assertEqual(client._tick, 1)
        message['map_def']['players'][0]['name'] = 'Changed'
        with self.assertRaisesRegex(ValueError, 'Recovery launch map mismatch'):
            client._receive(client._peers[0], message)
        client._launch = None
        with self.assertRaisesRegex(ValueError, 'Unexpected recovery launch'):
            client._receive(client._peers[0], message)

    def test_lobby_messages_reject_schema_epoch_revision_and_unauthenticated_ack(self):
        from copy import deepcopy
        sessions = self.lobby(2)
        host, client = sessions
        client._peers[0].sock.shutdown(socket.SHUT_RDWR)
        pump([host], lambda: host.snapshot['status'] == 'recovering')
        original = _Peer.flush
        with patch.object(_Peer, 'flush', lambda p: None if p.target and b'recovery_lobby_ack' in p.tx else original(p)):
            pump(sessions, lambda: client._recovery.phase == 'lobby_install')
            offer = dict(type='recovery_lobby', epoch=host._recovery.epoch,
                         players=host.snapshot['players'], options=host.snapshot['options'], revision=host._revision)
            for field, value in (('extra', 1), ('epoch', True), ('revision', True),
                                 ('revision', -1), ('epoch', host._recovery.epoch + 1)):
                with self.subTest(field=field, value=value):
                    malformed = deepcopy(offer)
                    malformed[field] = value
                    with self.assertRaises(ValueError):
                        client._receive(client._peers[0], malformed)
            with socket.socket() as outsider:
                outsider.connect(('127.0.0.1', host.port))
                host.poll()
                pending = next(p for p in host._peers if p.slot is None)
                with self.assertRaisesRegex(ValueError, 'outside authenticated'):
                    host._receive(pending, dict(type='recovery_lobby_ack', epoch=host._recovery.epoch,
                                               revision=host._revision))

    def test_launch_delivery_and_tick_zero_wait_for_last_human_graph(self):
        for humans in (2, 3, 4):
            with self.subTest(humans=humans):
                sessions = self.lobby(humans)
                host = sessions[0]
                peer = next(p for p in host._peers if p.slot == humans-1)
                original = _Peer.flush
                with patch.object(_Peer, 'flush', lambda p: None if p is peer else original(p)):
                    host.start()
                    peer.sock.sendall(bytes(peer.tx[:9]))
                    del peer.tx[:9]
                    for _ in range(10):
                        for s in sessions:
                            s.poll()
                    self.assertIsNone(sessions[-1].launch)
                    managers = [GameManager.start_skirmish(s.launch['map_def']) for s in sessions[:-1]]
                    for _ in range(10):
                        for s, m in zip(sessions, managers):
                            self.assertFalse(s.advance(m, FIXED_DT))
                            self.assertEqual(m.state.tick, 0)
                    self.assertNotIn(0, host._frames)
                pump(sessions, lambda: all(s.launch for s in sessions))
                managers.append(GameManager.start_skirmish(sessions[-1].launch['map_def']))
                self.align(sessions, managers, 8)
                for s in sessions:
                    s.close()

    def test_lobby_launch_retry_has_one_absolute_grace(self):
        sessions = self.lobby(2)
        host, client = sessions
        now = [100.]
        client._recovery.clock = lambda: now[0]
        client._peers[0].sock.shutdown(socket.SHUT_RDWR)
        client.poll()
        self.assertEqual(client.snapshot['status'], 'recovering')
        self.assertIsNone(client.launch)
        self.assertEqual(client._recovery.deadline, 160.)
        client._recovery.retry_at = float('inf')
        now[0] = 159.
        client.poll()
        self.assertEqual(client._recovery.deadline, 160.)
        now[0] = 160.
        client.poll()
        self.assertEqual(client.snapshot['status'], 'error')
        self.assertIn('grace expired', client.snapshot['error'])

    def test_invalid_recovery_launch_map_is_terminal(self):
        from copy import deepcopy
        sessions = self.lobby(2)
        host, client = sessions
        host.start()
        client._recovery.begin()
        message = dict(type='recovery_launch', map_def=deepcopy(host.launch['map_def']),
                       players=host.snapshot['players'], options=host.snapshot['options'],
                       revision=host.snapshot['revision'])
        message['map_def']['players'][0]['name'] = 'Changed'
        with self.assertRaisesRegex(ValueError, 'Start map mismatch'):
            client._receive(client._peers[0], message)
        self.assertIsNone(client.launch)

    def test_initial_launch_loss_recovers_in_distinct_processes(self):
        self.independent_loss(prelaunch=False)

    def test_ready_lobby_loss_recovers_in_distinct_processes(self):
        self.independent_loss(prelaunch=True)

    def test_drive_to_tick_finishes_its_own_tick_after_the_peer_reports_done(self):
        """The peer's 'done' is not proof the parent finished driving.

        On a loaded Windows runner the recovery handshake consumed enough loop
        iterations that the isolated peer posted 'done' at tick eight while the
        parent had only advanced to six. Breaking on that message asserted the
        lagged tick, so identical bytes went red on a slow machine and green on a
        fast one. The loop must finish driving its own manager to the target
        before it compares checksums.
        """
        class FakeParent:
            def __init__(self):
                self.queued = [('done', 1, 8, 'peer-checksum', 1)]
            def poll(self):
                return bool(self.queued)
            def recv(self):
                return self.queued.pop(0)
        class FakeHost:
            def __init__(self):
                self.snapshot = {'status': 'lobby'}
                self.advances = 0
            def poll(self):
                return None
            def recovery_step(self, manager):
                return None
            def take_restored_manager(self):
                return None
            def acknowledge_install(self, manager):
                return None
            def advance(self, manager, dt):
                self.advances += 1
                manager.state.tick += 1
        class FakeManager:
            def __init__(self):
                self.state = SimpleNamespace(tick=6)
        host, manager, parent = FakeHost(), FakeManager(), FakeParent()
        manager, installed, result = self.drive_to_tick(host, manager, parent)
        self.assertIsNotNone(result)
        assert result is not None
        self.assertEqual((manager.state.tick, installed, result[0]), (8, False, 'done'))
        self.assertEqual(host.advances, 2)

    def independent_loss(self, prelaunch):
        options = default_lan_options()
        options.update(human_count=2, ai_count=0, map_id='skirmish04')
        host = LanSession.host(free_port(), options, recovery=True)
        self.addCleanup(host.close)
        ctx = multiprocessing.get_context('spawn')
        parent, child = ctx.Pipe()
        self.addCleanup(parent.close)
        process = ctx.Process(target=isolated_client, args=(host.port, child, prelaunch))
        process.start()
        child.close()
        def cleanup():
            if process.is_alive():
                process.terminate()
            process.join(5)
        self.addCleanup(cleanup)
        host.set_ready(True)
        pump([host], lambda: host.snapshot['can_start'] and parent.poll(), seconds=15)
        ready = parent.recv()
        self.assertEqual(ready[0], 'ready', ready)
        self.assertNotEqual(ready[1], os.getpid())
        peer = host._peers[0]
        original = _Peer.flush
        if prelaunch:
            peer.sock.shutdown(socket.SHUT_RDWR)
            pump([host], lambda: host.snapshot['status'] == 'recovering')
            self.assertIsNone(host.launch)
        else:
            with patch.object(_Peer, 'flush', lambda p: None if p is peer else original(p)):
                host.start()
                peer.sock.shutdown(socket.SHUT_RDWR)
        parent.send('go')
        if prelaunch:
            pump([host], lambda: host.snapshot['status'] == 'lobby', seconds=15)
            host.start()
        manager = GameManager.start_skirmish(host.launch['map_def'])
        manager.state._net_session = host
        manager, installed, result = self.drive_to_tick(host, manager, parent)
        self.assertIsNotNone(result)
        self.assertEqual(result[0], 'done', result)
        self.assertEqual(installed, not prelaunch)
        self.assertEqual(manager.state.tick, 8)
        self.assertEqual(result[2:], (8, precise_checksum(manager), 1))
        parent.send('close')
        process.join(5)
        self.assertEqual(process.exitcode, 0)

    def drive_to_tick(self, host, manager, parent, target=8, seconds=15):
        """Drive the host's own manager to ``target`` before believing the peer.

        The isolated peer reports when *it* reached the target; on a slow runner
        that can happen while this process is still short of it, because recovery
        steps consumed the loop's iterations. Breaking on the peer's message
        therefore asserted a lagged tick, so identical bytes passed on a fast
        machine and failed on a slow one. Keep advancing after the message until
        this side reaches the target, then let the caller compare checksums.
        """
        installed = False
        result = None
        end = time.monotonic() + seconds
        while time.monotonic() < end:
            host.poll()
            status = host.snapshot['status']
            if status == 'error':
                raise AssertionError(host.snapshot)
            if status == 'recovering':
                host.recovery_step(manager)
                candidate = host.take_restored_manager()
                if candidate is not None:
                    manager = candidate
                    manager.state._net_session = host
                    host.acknowledge_install(manager)
                    installed = True
            elif manager.state.tick < target:
                host.advance(manager, FIXED_DT)
            if parent.poll():
                result = parent.recv()
            if result is not None and manager.state.tick >= target:
                break
            time.sleep(.001)
        return manager, installed, result

    def lobby(self, humans):
        options = default_lan_options()
        options.update(human_count=humans, ai_count=0, map_id='skirmish04')
        host = LanSession.host(free_port(), options, recovery=True)
        sessions = [host]
        self.addCleanup(host.close)
        for index in range(1, humans):
            client = LanSession.join('127.0.0.1', host.port, recovery=True)
            sessions.append(client)
            self.addCleanup(client.close)
        pump(sessions, lambda: all(len(s.snapshot['players']) == humans for s in sessions))
        for s in sessions:
            s.set_ready(True)
        pump(sessions, lambda: all(all(p['ready'] for p in s.snapshot['players']) for s in sessions))
        self.assertIsNotNone(sessions[1]._recovery.credential)
        return sessions

    def test_lost_or_partial_start_recovers_original_slots_before_tick_zero(self):
        for humans in (2, 3, 4):
            for partial in (False, True):
                with self.subTest(humans=humans, partial=partial):
                    sessions = self.lobby(humans)
                    host, client = sessions[:2]
                    peer = next(p for p in host._peers if p.slot == 1)
                    original = _Peer.flush
                    def held(p):
                        if p is not peer:
                            original(p)
                    with patch.object(_Peer, 'flush', held):
                        host.start()
                        if partial:
                            # Deliver a real incomplete start header/body, not a
                            # synthetic parser state or a received launch object.
                            peer.sock.sendall(bytes(peer.tx[:9]))
                            client.poll()
                            self.assertIsNone(client.launch)
                        peer.sock.shutdown(socket.SHUT_RDWR)
                    pump(sessions, lambda: all(s.launch is not None for s in sessions))
                    self.assertEqual([s.local_player for s in sessions], list(range(humans)))
                    managers = [GameManager.start_skirmish(s.launch['map_def']) for s in sessions]
                    for s, m in zip(sessions, managers):
                        m.state._net_session = s
                    self.assertEqual([m.state.tick for m in managers], [0]*humans)
                    self.recover(sessions, managers)
                    self.align(sessions, managers, 8)
                    for s in sessions:
                        s.close()

    def test_start_flush_eof_is_recoverable_not_explicit_abort(self):
        sessions = self.lobby(2)
        host = sessions[0]
        peer = host._peers[0]
        original = _Peer.flush
        def broken(p):
            if p is peer:
                raise ConnectionError('Disconnected')
            original(p)
        with patch.object(_Peer, 'flush', broken):
            host.start()
        self.assertEqual(host.snapshot['status'], 'recovering', host.snapshot)
        pump(sessions, lambda: all(s.launch for s in sessions))
        managers = [GameManager.start_skirmish(s.launch['map_def']) for s in sessions]
        self.recover(sessions, managers)
        self.align(sessions, managers, 5)
