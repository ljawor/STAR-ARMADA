#!/usr/bin/env python3
"""Real TCP proof of reconnect PRIMITIVES at an externally quiesced barrier.

This is not a LanSession/main reconnect acceptance test. The normal production
session still terminates on disconnect. Run: PYTHONPATH=. .venv/bin/python
 tools/diag_lan_reconnect.py
"""
import base64
import hashlib
import json
import socket
import time
from contextlib import ExitStack

from game.core.commands import StopCommand, PlayerCommand
from game.core.manager import GameManager
from game.data.store import DataStore
from game.net.lan import (_Peer, _json, build_lan_map, default_lan_options,
                          content_hash, precise_checksum, FIXED_DT, INPUT_DELAY)
from game.net.reconnect import (RecoveryBarrier, PendingInputs, capture_snapshot,
                                restore_snapshot, ChunkSender, ChunkReceiver)


def _read(peer, timeout=3.):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        messages = peer.poll()
        if messages:
            return messages
    raise AssertionError('Diagnostic TCP read timed out')


def _acknowledge_connection(barrier, expected_slot, ack, *, now):
    """expected_slot is the host's authenticated peer-map key, never wire data."""
    if (type(ack) is not dict or set(ack) != {'type', 'slot', 'epoch', 'tick', 'digest'}
            or ack['type'] != 'recovery_ack' or type(ack['slot']) is not int
            or ack['slot'] != expected_slot):
        raise ValueError('Recovery acknowledgement connection slot mismatch')
    barrier.acknowledge(expected_slot, epoch=ack['epoch'], tick=ack['tick'],
                        digest=ack['digest'], now=now)


def run_scenario(humans):
    with ExitStack() as stack:
        listener = stack.enter_context(socket.socket())
        listener.bind(('127.0.0.1', 0))
        listener.listen(4)
        address = listener.getsockname()

        def pair():
            sock = socket.create_connection(address, timeout=3.)
            server, _ = listener.accept()
            host, client = _Peer(server), _Peer(sock)
            stack.callback(host.close)
            stack.callback(client.close)
            return host, client

        peers = {slot: pair() for slot in range(1, humans)}
        options = default_lan_options()
        options.update(human_count=humans, ai_count=min(1, 4-humans), map_id='skirmish04')
        gm = GameManager.start_skirmish(build_lan_map(DataStore.get(), options))
        for _ in range(37):
            gm.step(FIXED_DT)
        tick = gm.state.tick
        ledger = PendingInputs(humans, barrier_tick=tick)
        for slot in range(humans):
            ship = next(e for e in gm.state.entities.values() if e.owner == slot and e.is_ship)
            ledger.accept(slot, sequence=0, target_tick=tick+INPUT_DELAY,
                          commands=[StopCommand(slot, [ship.id]).to_dict()])
        # Repeat an unconfirmed local submission: canonical ledger retains ONE.
        entry = ledger.export()['entries'][1]
        assert not ledger.accept(entry['slot'], sequence=entry['sequence'],
                                 target_tick=entry['target_tick'], commands=entry['commands'])
        snapshot = capture_snapshot(gm)
        bundle = _json(dict(snapshot=base64.b64encode(snapshot).decode('ascii'), pending=ledger.export()))
        digest = hashlib.sha256(bundle).hexdigest()
        barrier = RecoveryBarrier(humans, content_hash(gm.ds))
        token = barrier.credentials(1)
        peers[1][1].close()  # actual socket loss, not a mocked exception
        disconnected = False
        try:
            _read(peers[1][0])
        except ConnectionError:
            disconnected = True
        assert disconnected
        peers[1][0].close()
        barrier.interrupt(1, tick=tick, digest=digest, now=100.)
        frozen_hash = precise_checksum(gm)
        # Other connections continue carrying traffic, not simulation ticks.
        for slot in range(2, humans):
            peers[slot][1].send(dict(type='ping'))
            peers[slot][1].flush()
            assert _read(peers[slot][0]) == [dict(type='ping')]
        barrier.poll(now=120.)
        assert gm.state.tick == tick and precise_checksum(gm) == frozen_hash
        peers[1] = pair()  # same numeric host/port; no host migration
        host, client = peers[1]
        invalid = dict(token, token='invalid-replayed-token', content=barrier.content)
        client.send(dict(type='resume', slot=1, credentials=invalid))
        client.flush()
        message = _read(host)[0]
        invalid_rejected = False
        try:
            barrier.authenticate(message['slot'], **message['credentials'], now=121.)
        except ValueError:
            invalid_rejected = True
        assert invalid_rejected and barrier.status == 'paused'
        client.send(dict(type='resume', slot=1, credentials=dict(token, content=barrier.content)))
        client.flush()
        message = _read(host)[0]
        barrier.authenticate(message['slot'], **message['credentials'], now=122.)
        managers = [gm]
        ledgers = [ledger]
        barrier.acknowledge(0, epoch=barrier.epoch, tick=tick, digest=digest, now=123.)
        max_tx = 0
        for slot in range(1, humans):
            host, client = peers[slot]
            sender, receiver = ChunkSender(bundle), ChunkReceiver(digest)
            received = None
            deadline = time.monotonic()+3.
            while received is None and time.monotonic() < deadline:
                sender.pump(host)
                max_tx = max(max_tx, len(host.tx))
                host.flush()
                for message in client.poll():
                    data = receiver.receive(message)
                    if data is not None:
                        received = data
            assert isinstance(received, bytes) and received == bundle
            packet = json.loads(received)
            restored = restore_snapshot(base64.b64decode(packet['snapshot'], validate=True))
            restored_ledger = PendingInputs.restore(packet['pending'])
            assert precise_checksum(restored) == precise_checksum(gm)
            assert restored_ledger.export() == ledger.export()
            managers.append(restored)
            ledgers.append(restored_ledger)
            client.send(dict(type='recovery_ack', slot=slot, epoch=barrier.epoch,
                             tick=restored.state.tick, digest=hashlib.sha256(received).hexdigest()))
            client.flush()
            ack = _read(host)[0]
            _acknowledge_connection(barrier, slot, ack, now=124.)
            assert barrier.can_resume == (slot == humans-1)
        barrier.finish(now=125.)
        counts = [0]*humans
        for _ in range(60):
            for index, (manager, pending) in enumerate(zip(managers, ledgers)):
                due = pending.for_tick(manager.state.tick)
                counts[index] += len(due)
                manager.state.command_queue.extend(PlayerCommand.from_dict(c) for c in due)
                executed_tick = manager.state.tick
                manager.step(FIXED_DT)
                pending.commit_through(executed_tick)
            assert len({manager.state.tick for manager in managers}) == 1
            assert len({precise_checksum(manager) for manager in managers}) == 1
        assert counts == [humans]*humans
        # A second actual interruption exercises true replay of an old rotated
        # credential, rather than only a malformed token string.
        peers[1][1].close()
        try:
            _read(peers[1][0])
            raise AssertionError('Second EOF not observed')
        except ConnectionError:
            pass
        peers[1][0].close()
        barrier.interrupt(1, tick=gm.state.tick, digest=digest, now=200.)
        peers[1] = pair()
        host, client = peers[1]
        client.send(dict(type='resume', slot=1, credentials=dict(token, content=barrier.content)))
        client.flush()
        request = _read(host)[0]
        stale_rejected = False
        try:
            barrier.authenticate(request['slot'], **request['credentials'], now=201.)
        except ValueError:
            stale_rejected = True
        assert stale_rejected and barrier.status == 'paused'
        # Real TCP heartbeat traffic plus fake transport monotonic time: zero
        # sleeps and no wallclock in manager.step, fixed 60-second policy budget.
        for now in (205., 220., 245., 259., 260.):
            client.send(dict(type='ping'))
            client.flush()
            assert _read(host) == [dict(type='ping')]
            barrier.poll(now=now)
        grace_terminal = barrier.status == 'error' and not barrier.can_resume
        assert grace_terminal
        # Explicit abort and host loss are independent terminal scenarios.
        abort_policy = RecoveryBarrier(humans, barrier.content)
        abort_policy.interrupt(1, tick=gm.state.tick, digest=digest, now=300.)
        client.send(dict(type='abort'))
        client.flush()
        assert _read(host) == [dict(type='abort')]
        abort_policy.abort()
        abort_terminal = abort_policy.status == 'error' and not abort_policy.can_resume
        host_loss = RecoveryBarrier(humans, barrier.content)
        host.close()
        listener.close()
        try:
            _read(client)
            raise AssertionError('Host EOF not observed')
        except ConnectionError:
            host_loss.host_lost()
        host_loss_terminal = host_loss.status == 'error' and not host_loss.can_resume
        assert abort_terminal and host_loss_terminal
        return dict(scope='externally-quiesced foundation, not production reconnect',
                    humans=humans, aligned_ticks=60, snapshot_bytes=len(snapshot),
                    max_tx_bytes=max_tx, human_commands_per_peer=counts,
                    disconnect_detected=disconnected, invalid_token_rejected=invalid_rejected,
                    stale_token_rejected=stale_rejected, grace_terminal=grace_terminal,
                    abort_terminal=abort_terminal, host_loss_terminal=host_loss_terminal)


if __name__ == '__main__':
    results = [run_scenario(humans) for humans in (2, 3, 4)]
    print(json.dumps(dict(result='LAN_RECONNECT_FOUNDATION_OK', scenarios=results), indent=2))
