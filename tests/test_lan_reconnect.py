"""Reconnect foundations; not a claim of live LanSession recovery."""
import unittest
from game.core.manager import GameManager
from game.core.commands import StopCommand
from game.data.store import DataStore
from game.net.lan import build_lan_map, default_lan_options, precise_checksum, FIXED_DT


class SnapshotTests(unittest.TestCase):
    def test_snapshot_rejects_command_object_replaced_by_identical_dict(self):
        import json
        from game.net.reconnect import capture_snapshot, restore_snapshot
        gm = self.manager()
        gm.state.command_queue.append(StopCommand(0, []))
        packet = json.loads(capture_snapshot(gm))
        def replace(node):
            if isinstance(node, list):
                if len(node) == 3 and node[:2] == ['object', 'PlayerCommand']:
                    node[:] = ['dict', [[['scalar', k], v] for k, v in node[2].items()]]
                    return
                for child in node:
                    replace(child)
            elif isinstance(node, dict):
                for child in node.values():
                    replace(child)
        replace(packet['body'])
        with self.assertRaises(ValueError):
            restore_snapshot(json.dumps(packet).encode())

    def test_snapshot_validates_runtime_graph_before_checksum(self):
        import json
        from game.net.reconnect import capture_snapshot, restore_snapshot, _decode, _encode
        from game.core.world import Fleet, Projectile
        from game.core.vectors import Vec3
        gm = self.manager()
        gm.step(FIXED_DT)  # AI brains are lazily initialized by the first tick.
        gm.state.fleets[1] = Fleet(1, 0, 'probe')
        gm.state.projectiles[1] = Projectile(1, 0, 'laser_cannon', Vec3(), Vec3(), 1, 1., 1., 1., 1., 1.)
        baseline = json.loads(capture_snapshot(gm))
        for typename in ('Entity', 'Projectile', 'PlayerState', 'Fleet', 'MapInfo', 'SubsystemState', 'Vec3'):
            packet = json.loads(json.dumps(baseline))
            def replace(node):
                if isinstance(node, list):
                    if len(node) == 3 and node[:2] == ['object', typename]:
                        node[:] = ['dict', [[['scalar', k], v] for k, v in node[2].items()]]
                        return True
                    return any(replace(child) for child in node)
                if isinstance(node, dict):
                    return any(replace(child) for child in node.values())
                return False
            self.assertTrue(replace(packet['body']))
            with self.subTest(type=typename), self.assertRaisesRegex(ValueError, 'schema'):
                restore_snapshot(json.dumps(packet).encode())
        for section, mutate in (
                ('state', lambda s: setattr(s['map_info'], 'bounds', 'bad')),
                ('state', lambda s: setattr(next(iter(s['entities'].values())), 'alive', 1)),
                ('state', lambda s: setattr(next(iter(s['entities'].values())), 'pos', Vec3(True, 0., 0.))),
                ('ai', lambda s: s.clear()),
                ('ai', lambda s: s[2].update(decision_timer='bad')),
                ('ai', lambda s: s[2].update(player_id=0)),
                ('systems', lambda s: s['trading'].update(_timer='bad')),
                ('systems', lambda s: s['mission'].update(completed=1)),
                ('systems', lambda s: s['mission']['script'].update(progress=[]))):
            packet = json.loads(json.dumps(baseline))
            graph = _decode(packet['body'][section])
            mutate(graph)
            packet['body'][section] = _encode(graph)
            with self.subTest(section=section, mutate=mutate), self.assertRaisesRegex(ValueError, 'schema'):
                restore_snapshot(json.dumps(packet).encode())

    def test_snapshot_rejects_malformed_ai_pending_site_vector(self):
        import json
        from game.net.reconnect import capture_snapshot, restore_snapshot, _decode, _encode
        gm = self.manager()
        gm.step(FIXED_DT)
        for pending, attack in (({1: ('mining_station', {'x': 0., 'y': 0., 'z': 0.})}, None),
                                ({}, [])):
            packet = json.loads(capture_snapshot(gm))
            brains = _decode(packet['body']['ai'])
            brains[2]['_pending_site'] = pending
            brains[2]['last_strategic']['attack_fleet_id'] = attack
            packet['body']['ai'] = _encode(brains)
            with self.subTest(pending=pending, attack=attack), self.assertRaisesRegex(ValueError, 'schema'):
                restore_snapshot(json.dumps(packet).encode())

    def test_snapshot_malformed_envelopes_and_bounded_decode_raise_valueerror(self):
        import json
        from game.net.reconnect import capture_snapshot, restore_snapshot
        baseline = json.loads(capture_snapshot(self.manager()))
        for malformed in ([], None, {}, dict(baseline, body=[]), dict(baseline, body={}),
                          dict(baseline, tick=True), dict(baseline, checksum=[])):
            with self.subTest(packet=type(malformed)), self.assertRaises(ValueError):
                restore_snapshot(json.dumps(malformed).encode())
        for node in (['object', [], {}], ['dict', [[['list', []], ['scalar', 1]]]],
                     ['set', [['list', []]]], ['scalar', 1e309]):
            packet = dict(baseline, body=dict(baseline['body'], state=node))
            with self.subTest(node=node), self.assertRaises(ValueError):
                restore_snapshot(json.dumps(packet).encode())
        node = ['scalar', 0]
        for _ in range(100):
            node = ['list', [node]]
        packet = dict(baseline, body=dict(baseline['body'], state=node))
        with self.assertRaisesRegex(ValueError, 'limit'):
            restore_snapshot(json.dumps(packet).encode())
        packet['body']['state'] = ['list', [['scalar', 0]] * 250001]
        with self.assertRaisesRegex(ValueError, 'limit'):
            restore_snapshot(json.dumps(packet).encode())

    def manager(self):
        options = default_lan_options()
        options.update(ai_count=1, map_id='skirmish04')
        return GameManager.start_skirmish(build_lan_map(DataStore.get(), options))

    def test_snapshot_restores_active_projectiles_fleets_and_jump_state(self):
        from game.net.reconnect import capture_snapshot, restore_snapshot
        from game.core.world import Fleet, Projectile
        from game.core.vectors import Vec3
        gm = self.manager()
        ship = next(e for e in gm.state.entities.values() if e.owner == 0 and e.is_ship)
        target = next(e for e in gm.state.entities.values() if e.owner == 1 and e.is_ship)
        ship.jump_charge = .456789012345678
        ship.jump_target = Vec3(ship.pos.x*.7, 0., ship.pos.z*.7)
        fleet = Fleet(gm.state.next_fleet_id, 0, 'Recovery probe')
        gm.state.next_fleet_id += 1
        fleet.member_ids = {ship.id}
        fleet.flagship_id = ship.id
        fleet._last_move_issue = .12345678901234
        fleet.rally_point = (ship.pos.x*.8, 0., ship.pos.z*.8)
        gm.state.fleets[fleet.id] = fleet
        ship.fleet_id = fleet.id
        projectile = Projectile(gm.state.next_projectile_id, 0, 'laser_cannon',
                                Vec3(target.pos.x-10., 0., target.pos.z), Vec3(300., 0., 0.),
                                target.id, 23.456789012345, 1., 1., 1., .2345678901234,
                                attacker_entity_id=ship.id)
        gm.state.next_projectile_id += 1
        gm.state.projectiles[projectile.id] = projectile
        restored = restore_snapshot(capture_snapshot(gm))
        self.assertEqual(precise_checksum(restored), precise_checksum(gm))
        self.assertEqual(restored.state.fleets[fleet.id]._last_move_issue, fleet._last_move_issue)
        for _ in range(30):
            gm.step(FIXED_DT)
            restored.step(FIXED_DT)
            self.assertEqual(precise_checksum(gm), precise_checksum(restored))

    def test_snapshot_rejects_wrong_identity_corruption_and_campaign_managers(self):
        import json
        from game.net.reconnect import capture_snapshot, restore_snapshot, MAX_SNAPSHOT
        gm = self.manager()
        data = capture_snapshot(gm)
        for key, wrong in (('content', 'f'*64), ('version', 'obsolete'), ('protocol', -1),
                           ('tick', 123), ('checksum', '0'*64), ('format', 'replay')):
            with self.subTest(field=key):
                packet = json.loads(data)
                packet[key] = wrong
                with self.assertRaises(ValueError):
                    restore_snapshot(json.dumps(packet).encode())
        with self.assertRaises(ValueError):
            restore_snapshot(b'x'*(MAX_SNAPSHOT+1))
        gm.mission.mission = {'id': 'campaign-only'}
        with self.assertRaises(ValueError):
            capture_snapshot(gm)

    def test_full_snapshot_restores_ai_systems_queues_and_every_following_tick(self):
        import importlib.util
        self.assertIsNotNone(importlib.util.find_spec('game.net.reconnect'), 'full reconnect snapshot missing')
        from game.net import reconnect
        self.assertTrue(hasattr(reconnect, 'capture_snapshot'), 'full reconnect snapshot missing')
        gm = self.manager()
        for _ in range(37):
            gm.step(FIXED_DT)
        ship = next(e for e in gm.state.entities.values() if e.owner == 0 and e.is_ship)
        ship.retarget_cooldown = .123456789012345
        ship.weapon_cooldowns[0] = .23456789012345
        gm.state.command_queue.append(StopCommand(0, [ship.id]))
        gm.ai.ais[2].last_strategic['probe'] = gm.state.time
        before = precise_checksum(gm)
        snapshot = reconnect.capture_snapshot(gm)
        restored = reconnect.restore_snapshot(snapshot)
        self.assertEqual(before, precise_checksum(restored))
        self.assertIs(restored.weapons.state, restored.state)
        self.assertIs(restored.state._construction_system, restored.construction)
        self.assertIsNot(restored.state.entities[ship.id], ship)
        for _ in range(95):
            gm.step(FIXED_DT)
            restored.step(FIXED_DT)
            self.assertEqual(gm.state.tick, restored.state.tick)
            self.assertEqual(precise_checksum(gm), precise_checksum(restored), gm.state.tick)


class BarrierTests(unittest.TestCase):
    def test_malformed_ack_types_and_non_ascii_tokens_are_rejected(self):
        from game.net.reconnect import RecoveryBarrier
        b = RecoveryBarrier(2, 'c'*64)
        token = b.credentials(1)
        b.interrupt(1, tick=42, digest='d'*64, now=100.)
        with self.assertRaises(ValueError):
            b.authenticate(1, **dict(token, token='é'*64), content='c'*64, now=101.)
        self.assertEqual(b.status, 'paused')
        with self.assertRaises(ValueError):
            b.acknowledge(0, epoch=True, tick=42, digest='d'*64, now=102.)
        self.assertEqual(b.status, 'error')

    def test_resume_credentials_remain_stable_during_grace_and_check_build_protocol(self):
        from game.net.reconnect import RecoveryBarrier
        b = RecoveryBarrier(2, 'c'*64)
        token = b.credentials(1)
        b.interrupt(1, tick=42, digest='d'*64, now=100.)
        self.assertEqual(b.credentials(1), token)
        for changed in ({'version': 'obsolete'}, {'protocol': -1}):
            request = dict(token, content='c'*64)
            request.update(changed)
            with self.assertRaises(ValueError):
                b.authenticate(1, **request, now=101.)
        b.authenticate(1, **token, content='c'*64, now=102.)

    def test_absolute_deadline_survives_heartbeats_second_disconnect_and_loading(self):
        from game.net.reconnect import RecoveryBarrier
        b = RecoveryBarrier(3, 'c'*64)
        b.interrupt(1, tick=42, digest='d'*64, now=100.)
        b.interrupt(2, tick=42, digest='d'*64, now=150.)
        self.assertEqual(b.deadline, 160., 'a second disconnect must not extend grace')
        self.assertEqual(b.epoch, 1)
        for now in (150., 159.999, 160.):
            b.poll(now=now)
        self.assertEqual(b.status, 'error')
        self.assertFalse(b.can_resume)
        self.assertIn('grace', b.error)
        with self.assertRaises(ValueError):
            b.interrupt(1, tick=42, digest='d'*64, now=161.)

    def test_stale_wrong_incompatible_credentials_do_not_end_continuing_peer_session(self):
        from game.net.reconnect import RecoveryBarrier
        b = RecoveryBarrier(3, 'c'*64)
        token = b.credentials(1)
        b.interrupt(1, tick=42, digest='d'*64, now=100.)
        for changed in ({'token': 'wrong'}, {'session': 'old'}, {'generation': -1},
                        {'content': 'e'*64}):
            request = dict(token, content='c'*64)
            request.update(changed)
            with self.assertRaises(ValueError):
                b.authenticate(1, **request, now=101.)
            self.assertEqual(b.status, 'paused')
        b.acknowledge(0, epoch=1, tick=42, digest='d'*64, now=102.)
        b.acknowledge(2, epoch=1, tick=42, digest='d'*64, now=102.)
        self.assertFalse(b.can_resume)
        b.authenticate(1, **token, content='c'*64, now=159.)
        b.poll(now=160.)  # authenticated but loading has not finished
        self.assertEqual(b.status, 'error')

    def test_abort_host_loss_and_authenticated_hash_mismatch_are_terminal(self):
        from game.net.reconnect import RecoveryBarrier
        for cause in ('abort', 'host_lost', 'hash'):
            b = RecoveryBarrier(2, 'c'*64)
            b.interrupt(1, tick=42, digest='d'*64, now=100.)
            if cause == 'hash':
                with self.assertRaises(ValueError):
                    b.acknowledge(0, epoch=1, tick=42, digest='e'*64, now=101.)
            else:
                getattr(b, cause)()
            self.assertEqual(b.status, 'error', cause)
            self.assertFalse(b.can_resume)

    def test_authenticated_same_host_barrier_requires_every_peer_ack(self):
        from game.net import reconnect
        self.assertTrue(hasattr(reconnect, 'RecoveryBarrier'), 'recovery barrier missing')
        for humans in (2, 3, 4):
            with self.subTest(humans=humans):
                b = reconnect.RecoveryBarrier(humans, 'c'*64)
                token = b.credentials(1)
                b.interrupt(1, tick=42, digest='d'*64, now=100.)
                self.assertEqual(b.deadline, 160.)
                self.assertFalse(b.can_resume)
                b.authenticate(1, **token, content='c'*64, now=101.)
                for slot in range(humans):
                    b.acknowledge(slot, epoch=b.epoch, tick=42, digest='d'*64, now=102.)
                    self.assertEqual(b.can_resume, slot == humans-1)
                b.finish(now=103.)
                self.assertEqual(b.status, 'running')
                self.assertNotEqual(b.credentials(1)['token'], token['token'])


class PendingInputTests(unittest.TestCase):
    def test_restore_requires_exact_outstanding_sequences_without_duplicates(self):
        from game.net.reconnect import PendingInputs
        ledger = PendingInputs(2, barrier_tick=42)
        ledger.accept(1, sequence=0, target_tick=43, commands=[])
        ledger.accept(1, sequence=1, target_tick=44, commands=[])
        baseline = ledger.export()
        import copy
        for entries in ([], baseline['entries'][1:], baseline['entries'][:1],
                        baseline['entries'] + baseline['entries'][:1]):
            data = copy.deepcopy(baseline)
            data['entries'] = copy.deepcopy(entries)
            with self.subTest(entries=entries), self.assertRaises(ValueError):
                PendingInputs.restore(data)
        restored = PendingInputs.restore(baseline)
        self.assertEqual(restored.export(), baseline)
        ledger.commit_through(43)
        self.assertEqual(PendingInputs.restore(ledger.export()).export(), ledger.export())

    def test_restore_rejects_malformed_entry_and_envelope_schemas(self):
        from game.net.reconnect import PendingInputs
        import copy
        ledger = PendingInputs(2, barrier_tick=42)
        ledger.accept(1, sequence=0, target_tick=43, commands=[])
        baseline = ledger.export()
        for bad in (None, [], {}, {'slot': 1}, dict(baseline['entries'][0], extra=1),
                    dict(baseline['entries'][0], slot=True),
                    dict(baseline['entries'][0], sequence=True),
                    dict(baseline['entries'][0], commands={})):
            packet = copy.deepcopy(baseline)
            packet['entries'] = [bad]
            with self.subTest(entry=bad), self.assertRaises(ValueError):
                PendingInputs.restore(packet)
        for bad in (None, [], {}, dict(baseline, humans=True), dict(baseline, next=[0, True])):
            with self.subTest(envelope=bad), self.assertRaises(ValueError):
                PendingInputs.restore(bad)

    def test_pending_inputs_cannot_overfill_a_turn_or_reverse_sequence_target_time(self):
        from game.net.reconnect import PendingInputs
        ledger = PendingInputs(2, barrier_tick=42)
        batch = [StopCommand(1, [7]).to_dict()]*64
        ledger.accept(1, sequence=0, target_tick=45, commands=batch)
        with self.assertRaises(ValueError):
            ledger.accept(1, sequence=1, target_tick=45, commands=batch)
        with self.assertRaises(ValueError):
            ledger.accept(1, sequence=1, target_tick=44, commands=[])
        ledger.accept(1, sequence=1, target_tick=46, commands=[])
        data = ledger.export()
        data['spent'] = [-2, -1]
        with self.assertRaises(ValueError):
            PendingInputs.restore(data)

    def test_unconfirmed_delayed_input_retries_are_exactly_once_and_spent_input_rejected(self):
        from game.net import reconnect
        self.assertTrue(hasattr(reconnect, 'PendingInputs'), 'reconnect input ledger missing')
        ledger = reconnect.PendingInputs(3, barrier_tick=42)
        commands = [StopCommand(1, [7]).to_dict()]
        self.assertTrue(ledger.accept(1, sequence=0, target_tick=45, commands=commands))
        self.assertFalse(ledger.accept(1, sequence=0, target_tick=45, commands=commands))
        commands.clear()  # detached from local mutable submission
        self.assertEqual(len(ledger.for_tick(45)), 1)
        self.assertEqual(ledger.for_tick(42), [])
        with self.assertRaises(ValueError):
            ledger.accept(1, sequence=0, target_tick=45, commands=[])
        with self.assertRaises(ValueError):
            ledger.accept(1, sequence=2, target_tick=45, commands=[])
        ledger.accept(0, sequence=0, target_tick=45, commands=[StopCommand(0, [8]).to_dict()])
        self.assertEqual([c['player'] for c in ledger.for_tick(45)], [0, 1])
        restored = reconnect.PendingInputs.restore(ledger.export())
        self.assertEqual(restored.export(), ledger.export())
        ledger.commit_through(45)
        self.assertEqual(ledger.for_tick(45), [])
        with self.assertRaises(ValueError):
            ledger.accept(1, sequence=0, target_tick=45, commands=[StopCommand(1, [7]).to_dict()])
        self.assertTrue(ledger.accept(1, sequence=1, target_tick=46, commands=[]))


class ChunkTests(unittest.TestCase):
    def test_chunk_receiver_rejects_oversize_reordering_truncation_and_corruption(self):
        import base64
        import hashlib
        from game.net.reconnect import ChunkReceiver, MAX_SNAPSHOT
        payload = b'abc'
        digest = hashlib.sha256(payload).hexdigest()
        header = dict(type='snapshot_begin', transfer='a'*32, size=3, digest=digest)
        good = dict(type='snapshot_chunk', transfer='a'*32, index=0,
                    data=base64.b64encode(payload).decode())
        with self.assertRaises(ValueError):
            ChunkReceiver(digest).receive(dict(header, size=MAX_SNAPSHOT+1))
        for wrong in ({'index': 1}, {'transfer': 'b'*32}, {'data': '??'},
                      {'data': base64.b64encode(b'ab').decode()},
                      {'data': base64.b64encode(b'xyz').decode()}):
            with self.subTest(change=wrong):
                receiver = ChunkReceiver(digest)
                receiver.receive(header)
                with self.assertRaises(ValueError):
                    receiver.receive(dict(good, **wrong))
        receiver = ChunkReceiver(digest)
        receiver.receive(header)
        self.assertEqual(receiver.receive(good), payload)
        with self.assertRaises(ValueError):
            receiver.receive(good)

    def test_real_tcp_large_snapshot_is_chunked_bounded_and_verified(self):
        import socket
        import time
        from game.net import reconnect
        from game.net.lan import _Peer, MAX_FRAME, MAX_BUFFER
        self.assertTrue(hasattr(reconnect, 'ChunkSender'), 'bounded snapshot transfer missing')
        listener = socket.socket()
        self.addCleanup(listener.close)
        listener.bind(('127.0.0.1', 0))
        listener.listen()
        client = socket.create_connection(listener.getsockname())
        server, _ = listener.accept()
        tx, rx = _Peer(server), _Peer(client)
        self.addCleanup(tx.close)
        self.addCleanup(rx.close)
        data = b'snapshot-future-state-' * 55000  # larger than frame AND buffer
        sender = reconnect.ChunkSender(data)
        receiver = reconnect.ChunkReceiver(sender.digest)
        restored = None
        max_tx = 0
        start = time.monotonic()
        while restored is None and time.monotonic()-start < 5:
            sender.pump(tx)
            max_tx = max(max_tx, len(tx.tx))
            tx.flush()
            for message in rx.poll():
                self.assertLessEqual(len(__import__('json').dumps(message).encode()), MAX_FRAME)
                result = receiver.receive(message)
                if result is not None:
                    restored = result
        self.assertEqual(restored, data)
        self.assertLess(max_tx, MAX_BUFFER)
        self.assertTrue(sender.done)


class DiagnosticTests(unittest.TestCase):
    def test_acknowledgement_cannot_spoof_another_authenticated_connection_slot(self):
        import socket
        from tools import diag_lan_reconnect as diag
        from game.net.reconnect import RecoveryBarrier
        from game.net.lan import _Peer
        self.assertTrue(hasattr(diag, '_acknowledge_connection'), 'connection-bound ack handler missing')
        barrier = RecoveryBarrier(3, 'c'*64)
        credentials = barrier.credentials(1)
        barrier.interrupt(1, tick=42, digest='d'*64, now=100.)
        barrier.authenticate(1, **credentials, content='c'*64, now=101.)
        listener = socket.socket()
        self.addCleanup(listener.close)
        listener.bind(('127.0.0.1', 0))
        listener.listen()
        client = socket.create_connection(listener.getsockname())
        self.addCleanup(client.close)
        server, _ = listener.accept()
        self.addCleanup(server.close)
        host, peer = _Peer(server), _Peer(client)
        self.addCleanup(host.close)
        self.addCleanup(peer.close)
        barrier.acknowledge(0, epoch=1, tick=42, digest='d'*64, now=102.)
        for supplied_slot in (2, 0, True):
            peer.send(dict(type='recovery_ack', slot=supplied_slot, epoch=1, tick=42, digest='d'*64))
            peer.flush()
            message = diag._read(host)[0]
            with self.subTest(slot=supplied_slot), self.assertRaises(ValueError):
                diag._acknowledge_connection(barrier, 1, message, now=103.)
            self.assertEqual(barrier._acks, {0})
            self.assertFalse(barrier.can_resume)
        peer.send(dict(type='recovery_ack', slot=1, epoch=1, tick=42, digest='d'*64))
        peer.flush()
        diag._acknowledge_connection(barrier, 1, diag._read(host)[0], now=104.)
        self.assertEqual(barrier._acks, {0, 1})
        barrier.acknowledge(2, epoch=1, tick=42, digest='d'*64, now=104.)
        self.assertTrue(barrier.can_resume)

    def test_two_three_four_humans_real_tcp_disconnect_restore_and_following_ticks(self):
        import importlib.util
        self.assertIsNotNone(importlib.util.find_spec('tools.diag_lan_reconnect'),
                             'real TCP reconnect foundation diagnostic missing')
        from tools.diag_lan_reconnect import run_scenario
        for humans in (2, 3, 4):
            with self.subTest(humans=humans):
                result = run_scenario(humans)
                self.assertEqual(result['humans'], humans)
                self.assertEqual(result['aligned_ticks'], 60)
                self.assertEqual(result['human_commands_per_peer'], [humans]*humans)
                self.assertTrue(result['disconnect_detected'])
                self.assertTrue(result['invalid_token_rejected'])
                self.assertTrue(result.get('stale_token_rejected'), 'old rotated credential must be rejected')
                self.assertTrue(result.get('grace_terminal'), 'TCP heartbeat cannot prolong grace')
                self.assertTrue(result.get('abort_terminal'), 'explicit TCP abort must be terminal')
                self.assertTrue(result.get('host_loss_terminal'), 'real host socket loss must be terminal')


if __name__ == '__main__':
    unittest.main()
