"""Opt-in same-process trusted-LAN recovery. Bearers are NOT encrypted.

A released-frame drain, never rollback: ordinary advance remains paused. Callers
must explicitly drain, take the new graph, rebind, then acknowledge installation.
Unexpected EOF retries the original host; explicit shutdown is terminal. There
is no host migration. Credentials never enter public snapshots or recordings.
"""
from copy import deepcopy
import hashlib
import hmac
import json
import secrets
import socket
import time

from game.net.lan import (INPUT_DELAY, FIXED_DT, GAME_VERSION, PROTOCOL_VERSION,
                         _Peer, _commands, _digest, _json, _unique_object,
                         classify_connect_result, precise_checksum)
from game.net.reconnect import (capture_snapshot, restore_snapshot, ChunkSender,
                                ChunkReceiver, MAX_SNAPSHOT)


def schema(message, keys):
    if type(message) is not dict or set(message) != set(keys.split()):
        raise ValueError('Recovery message schema mismatch')


def integer(value):
    if type(value) is not int or value < 0:
        raise ValueError('Recovery integer schema mismatch')
    return value


class LiveRecovery:
    def __init__(self, session, clock=None):
        self.s = session
        self.clock = clock or time.monotonic
        self.session = secrets.token_hex(32) if session.is_host else None
        self.tokens = {}
        self.pending_tokens = None
        self.generation = 0
        self.credential = None
        self.address = session._peers[0].target if not session.is_host else None
        self.deadline = None
        self.epoch = 0
        self.phase = 'running'
        self.local = {}
        self.history = {t: dict(type='frame', tick=t, **deepcopy(f))
                        for t, f in session._frames.items()}
        self.reports = {}
        self.drained = {}
        self.target = None
        self.drain_frames = {}
        self.reported = False
        self.drain_reported = False
        self.senders = {}
        self.receiver = None
        self.report_receivers = {}
        self.bundle = None
        self.bundle_digest = None
        self.graph_digest = None
        self.manager = None
        self.delivered = False
        self.acks = set()
        self.retry_at = 0.

    @property
    def snapshot(self):
        connected = {0} | {p.slot for p in self.s._peers if p.slot is not None}
        return deepcopy(dict(status=self.s._status, phase=self.phase, epoch=self.epoch,
                             missing=sorted(set(range(self.s._options.get('human_count', 0))) - connected)
                             if self.s.is_host else ([] if self.s._peers else [0]),
                             remaining=max(0., self.deadline-self.clock()) if self.deadline is not None else None,
                             tick=self.target))

    def check(self):
        if self.deadline is not None and self.clock() >= self.deadline:
            raise ValueError('Reconnect grace expired')

    def private(self, peer, *, pending=False):
        tokens = self.pending_tokens if pending else self.tokens
        peer.send(dict(type='recovery_private', session=self.session,
                       token=tokens[peer.slot], generation=self.generation+int(pending)))

    def admitted(self, peer):
        self.tokens[peer.slot] = secrets.token_hex(32)
        self.private(peer)

    def sealed(self, message):
        self.local[message['tick']] = deepcopy(message)
        self.trim()

    def trim(self):
        floor = self.s._tick - 2 * INPUT_DELAY - 1
        self.local = {t: b for t, b in self.local.items() if t >= floor}
        self.history = {t: f for t, f in self.history.items() if t >= floor}

    def released(self, frame):
        self.history[frame['tick']] = deepcopy(frame)
        self.trim()

    def reset(self):
        self.host_frozen = self.s.is_host
        self.phase = 'freeze'
        self.reports = {}
        self.drained = {}
        self.target = None
        self.reported = self.drain_reported = False
        self.senders = {}
        self.receiver = None
        self.manager = None
        self.delivered = False
        self.acks = set()
        self.bundle = None

    def begin(self):
        if self.deadline is None:
            self.deadline = self.clock() + 60.
        self.check()
        self.s._status = 'recovering'
        self.reset()
        if self.s.is_host:
            self.epoch += 1
            self.s._broadcast(self.freeze_message())

    def freeze_message(self):
        return dict(type='recovery_freeze', epoch=self.epoch,
                    remaining=max(0., self.deadline-self.clock()))

    def lost(self, peer):
        s = self.s
        if s._status not in ('running', 'recovering') or (s.is_host and peer.slot is None):
            return False
        if not s.is_host and self.credential is None:
            return False
        peer.close()
        self.report_receivers.pop(peer, None)
        if peer in s._peers:
            s._peers.remove(peer)
        self.begin()
        return True

    def abort(self):
        self.s._fail('Reconnect explicitly aborted')

    def poll(self):
        self.check()
        s = self.s
        if s._status != 'recovering':
            return
        if not s.is_host and not s._peers and self.clock() >= self.retry_at:
            self.retry_at = self.clock() + .1
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            peer = _Peer(sock)
            peer.target = self.address
            verdict = classify_connect_result(sock.connect_ex(self.address))
            if verdict == 'failed':
                sock.close()
            else:
                peer.connected = verdict == 'connected'
                s._peers.append(peer)
                peer.send(dict(type='recovery_auth', slot=s.local_player,
                               content=s._content, version=GAME_VERSION, protocol=PROTOCOL_VERSION,
                               **self.credential))
        for peer, sender in list(self.senders.items()):
            if peer in s._peers:
                sender.pump(peer)
        if s.is_host and self.phase == 'freeze' and len(self.reports) == s._options['human_count']:
            ticks = [r['tick'] for r in self.reports.values()]
            self.target = max(ticks)
            if self.target-min(ticks) > INPUT_DELAY:
                raise ValueError('Recovery tick skew exceeds released pipeline')
            self.drain_frames = {}
            for t in range(min(ticks), self.target):
                if t not in self.history:
                    raise ValueError('Missing authoritative drain frame')
                self.drain_frames[t] = deepcopy(self.history[t])
            self.phase = 'drain'
            instruction = dict(type='recovery_drain', epoch=self.epoch, tick=self.target,
                               frames=[deepcopy(f) for t, f in sorted(self.drain_frames.items())])
            data = _json(instruction)
            for peer in s._peers:
                if peer.slot is not None:
                    sender = ChunkSender(data)
                    peer.send(dict(type='recovery_drain_begin', epoch=self.epoch,
                                   tick=self.target, digest=sender.digest))
                    self.senders[peer] = sender

    def receive(self, peer, m):
        kind = m.get('type')
        s = self.s
        if kind == 'recovery_shutdown':
            schema(m, 'type')
            if s.is_host and peer.slot is None:
                raise ValueError('Unauthenticated shutdown')
            raise ValueError('Participant explicitly shut down; reconnect aborted')
        if kind == 'hello' and s.is_host:
            if m.get('recovery') is not True:
                raise ValueError('Recovery opt-in mismatch')
            return False
        if kind == 'recovery_private' and not s.is_host:
            schema(m, 'type session token generation')
            if not _digest(m['session']) or not _digest(m['token']):
                raise ValueError('Invalid private credentials')
            integer(m['generation'])
            self.credential = {k: m[k] for k in ('session', 'token', 'generation')}
            return True
        if kind == 'recovery_auth' and s.is_host:
            schema(m, 'type slot session token generation content version protocol')
            self.check()
            slot = m['slot']
            tokens = self.tokens if m['generation'] == self.generation else (
                self.pending_tokens if m['generation'] == self.generation+1 else None)
            if (peer.slot is not None or s._status != 'recovering' or type(slot) is not int
                    or tokens is None or slot not in tokens or any(p.slot == slot for p in s._peers)
                    or m['session'] != self.session or type(m['generation']) is not int
                    or m['content'] != s._content
                    or m['version'] != GAME_VERSION or type(m['protocol']) is not int
                    or m['protocol'] != PROTOCOL_VERSION or not _digest(m['token'])
                    or not hmac.compare_digest(m['token'], tokens[slot])):
                raise ValueError('Invalid resume credentials')
            peer.slot = slot
            peer.send(self.freeze_message())
            return True
        if kind == 'recovery_freeze' and not s.is_host:
            schema(m, 'type epoch remaining')
            epoch = integer(m['epoch'])
            remaining = m['remaining']
            if type(remaining) not in (int, float) or not 0 < remaining <= 60 or epoch < self.epoch:
                raise ValueError('Invalid freeze deadline or epoch')
            self.deadline = min(self.deadline or float('inf'), self.clock()+remaining)
            self.check()
            if epoch != self.epoch or s._status != 'recovering' or self.phase == 'freeze':
                self.reset()
            self.epoch = epoch
            self.host_frozen = True
            s._status = 'recovering'
            return True
        if kind == 'ping':
            return False
        if s._status == 'recovering' and kind in ('input', 'frame'):
            s._receive_tick(peer, m)
            return True
        if not isinstance(kind, str) or not (kind.startswith('recovery_') or kind.startswith('snapshot_')):
            return False
        self.check()
        if 'epoch' in m:
            integer(m['epoch'])
        if 'tick' in m:
            integer(m['tick'])
        if s._status != 'recovering' or (s.is_host and peer.slot is None):
            raise ValueError('Recovery message outside authenticated epoch')
        if kind == 'recovery_report_begin' and s.is_host:
            schema(m, 'type epoch digest')
            if (not 0 < m['epoch'] <= self.epoch or not _digest(m['digest'])
                    or (m['epoch'] == self.epoch and self.phase != 'drain')):
                raise ValueError('Invalid recovery report manifest')
            previous = self.report_receivers.get(peer)
            if previous and previous[0] == m['epoch'] and not previous[1].done:
                raise ValueError('Overlapping recovery report transfer')
            # A second interruption can precede this already queued old manifest.
            # Reassemble it under the same caps, but never apply an old epoch.
            self.report_receivers[peer] = (m['epoch'], ChunkReceiver(m['digest']))
            return True
        if kind in ('snapshot_begin', 'snapshot_chunk') and s.is_host:
            if peer not in self.report_receivers:
                raise ValueError('Unexpected recovery report transfer')
            epoch, receiver = self.report_receivers[peer]
            data = receiver.receive(m)
            if data is not None and epoch == self.epoch:
                report = json.loads(data, object_pairs_hook=_unique_object)
                self.check()
                self.receive(peer, report)
            return True
        if kind == 'recovery_report' and s.is_host:
            schema(m, 'type epoch tick batches pending sealed checksum')
            report = self.validate_report(m, peer.slot)
            if 0 < m['epoch'] < self.epoch:
                return True  # Bounded old in-flight work cannot affect this epoch.
            if m['epoch'] != self.epoch or self.phase not in ('freeze', 'drain'):
                raise ValueError('Stale recovery report')
            destination = self.reports if self.phase == 'freeze' else self.drained
            if peer.slot in destination:
                raise ValueError('Duplicate recovery report')
            destination[peer.slot] = report
            return True
        if kind == 'recovery_drain_begin' and not s.is_host:
            schema(m, 'type epoch tick digest')
            if (m['epoch'] != self.epoch or self.phase != 'freeze' or not _digest(m['digest'])
                    or not s._tick <= m['tick'] <= s._tick+INPUT_DELAY):
                raise ValueError('Invalid drain transfer manifest')
            self.receiver = ChunkReceiver(m['digest'])
            self.receiver_purpose = 'drain'
            self.phase = 'drain_transfer'
            return True
        if kind == 'recovery_drain' and not s.is_host:
            schema(m, 'type epoch tick frames')
            if m['epoch'] != self.epoch or self.phase != 'drain_transfer':
                raise ValueError('Stale drain instruction')
            self.target = integer(m['tick'])
            if not s._tick <= self.target <= s._tick+INPUT_DELAY or type(m['frames']) is not list:
                raise ValueError('Invalid drain window')
            frames = {}
            for frame in m['frames']:
                self.validate_frame(frame)
                if frame['tick'] in frames:
                    raise ValueError('Duplicate drain frame')
                frames[frame['tick']] = frame
            if any(t not in frames for t in range(s._tick, self.target)):
                raise ValueError('Incomplete drain proof')
            self.drain_frames = frames
            self.phase = 'drain'
            return True
        if kind == 'recovery_bundle' and not s.is_host:
            schema(m, 'type epoch digest graph tick')
            if (m['epoch'] != self.epoch or self.phase != 'drain' or m['tick'] != self.target
                    or not _digest(m['digest']) or not _digest(m['graph'])):
                raise ValueError('Invalid recovery bundle manifest')
            self.bundle_digest, self.graph_digest = m['digest'], m['graph']
            self.receiver = ChunkReceiver(self.bundle_digest)
            self.receiver_purpose = 'bundle'
            self.phase = 'transfer'
            return True
        if kind in ('snapshot_begin', 'snapshot_chunk') and not s.is_host:
            if self.phase not in ('transfer', 'drain_transfer') or self.receiver is None:
                raise ValueError('Unexpected snapshot transfer')
            data = self.receiver.receive(m)
            if data is not None:
                if self.receiver_purpose == 'drain':
                    self.receive(peer, json.loads(data, object_pairs_hook=_unique_object))
                else:
                    self.install_bundle(data)
            return True
        if kind == 'recovery_ack' and s.is_host:
            schema(m, 'type epoch tick graph bundle')
            if not _digest(m['graph']) or not _digest(m['bundle']):
                raise ValueError('Recovery acknowledgement digest schema mismatch')
            if 0 < m['epoch'] < self.epoch:
                return True  # Never ACK or resume on an older epoch's graph.
            if (self.phase != 'install' or m['epoch'] != self.epoch or m['tick'] != self.target
                    or m['graph'] != self.graph_digest or m['bundle'] != self.bundle_digest
                    or peer.slot in self.acks):
                raise ValueError('Recovery acknowledgement mismatch')
            self.acks.add(peer.slot)
            self.finish()
            return True
        if kind == 'recovery_resume' and not s.is_host:
            schema(m, 'type epoch graph bundle')
            if (self.phase != 'install' or s.local_player not in self.acks
                    or m['epoch'] != self.epoch or m['graph'] != self.graph_digest
                    or m['bundle'] != self.bundle_digest):
                raise ValueError('Premature recovery resume')
            self.resume()
            return True
        raise ValueError('Unexpected authenticated recovery message')

    def validate_report(self, report, slot):
        integer(report['tick'])
        if not _digest(report['checksum']) or (report['sealed'] is not None and not _digest(report['sealed'])):
            raise ValueError('Invalid report checksum')
        _commands(report['pending'], slot)
        batches = report['batches']
        if type(batches) is not list or len(batches) > 3*INPUT_DELAY+3:
            raise ValueError('Recovery journal limit')
        previous = -1
        for batch in batches:
            schema(batch, 'type tick checksum commands')
            t = integer(batch['tick'])
            if (batch['type'] != 'input' or t <= previous or not _digest(batch['checksum'])
                    or not max(0, report['tick']-2*INPUT_DELAY-1) <= t <= report['tick']+INPUT_DELAY):
                raise ValueError('Invalid journal batch identity')
            _commands(batch['commands'], slot)
            previous = t
        return deepcopy(report)

    def validate_frame(self, frame):
        schema(frame, 'type tick commands checksum')
        integer(frame['tick'])
        if frame['type'] != 'frame' or (frame['checksum'] is not None and not _digest(frame['checksum'])):
            raise ValueError('Invalid recovery frame')
        if type(frame['commands']) is not list:
            raise ValueError('Invalid recovery commands')
        if frame['checksum'] is None and (frame['tick'] not in range(1, INPUT_DELAY) or frame['commands']):
            raise ValueError('Missing checksum outside empty startup frame')
        last = -1
        for command in frame['commands']:
            owner = command.get('player') if type(command) is dict else None
            if type(owner) is not int or not 0 <= owner < self.s._options['human_count'] or owner < last:
                raise ValueError('Invalid recovery frame ownership')
            _commands([command], owner)
            last = owner
        for slot in range(self.s._options['human_count']):
            _commands([c for c in frame['commands'] if c['player'] == slot], slot)

    def report(self, gm):
        self.trim()
        if gm.state.tick != self.s._tick:
            raise ValueError('Recovery simulation tick mismatch')
        return dict(type='recovery_report', epoch=self.epoch, tick=self.s._tick,
                    checksum=precise_checksum(gm), batches=[deepcopy(self.local[t]) for t in sorted(self.local)
                                                          if t >= self.s._tick],
                    pending=deepcopy(self.s._pending), sealed=self.s._sealed)

    def send_report(self, gm, drained=False):
        report = self.report(gm)
        if not drained:
            # Freeze only proves position; unspent intent is reconciled AFTER drain.
            report.update(batches=[], pending=[], sealed=None)
        if self.s.is_host:
            (self.drained if drained else self.reports)[0] = report
        else:
            if not self.s._peers or not self.host_frozen:
                return False
            peer = self.s._peers[0]
            if drained:
                data = _json(report)
                sender = ChunkSender(data)
                peer.send(dict(type='recovery_report_begin', epoch=self.epoch, digest=sender.digest))
                self.senders[peer] = sender
            else:
                peer.send(report)
        return True

    def step(self, gm):
        if self.s._status != 'recovering':
            return False
        try:
            self.check()
            if self.phase == 'freeze' and not self.reported:
                self.reported = self.send_report(gm)
            if self.phase == 'drain':
                if self.s._tick < self.target:
                    self.drain_one(gm)
                    return True
                if not self.drain_reported:
                    if self.s._tick == 0 and self.s._sealed is None:
                        # Re-establish initial barrier without executing tick zero.
                        digest = precise_checksum(gm)
                        self.s._sealed = digest
                        self.s._checksums[0] = self.s._checksums[INPUT_DELAY] = digest
                        self.sealed(dict(type='input', tick=0, checksum=digest, commands=[]))
                        self.sealed(dict(type='input', tick=INPUT_DELAY, checksum=digest,
                                         commands=self.s._pending))
                        self.s._pending = []
                    self.drain_reported = self.send_report(gm, True)
                if self.s.is_host and len(self.drained) == self.s._options['human_count']:
                    self.build_bundle(gm)
            return False
        except (ValueError, TypeError, KeyError, OverflowError, RecursionError) as exc:
            self.s._fail(str(exc), phase='recovery')
            return False

    def drain_one(self, gm):
        s = self.s
        if gm.state.tick != s._tick:
            raise ValueError('Drain tick mismatch')
        if s._sealed is None:
            s._sealed = precise_checksum(gm)
            target = s._tick+INPUT_DELAY
            s._checksums[target] = s._sealed
            self.sealed(dict(type='input', tick=target, checksum=s._sealed, commands=s._pending))
            s._pending = []
        frame = self.drain_frames[s._tick]
        if frame['checksum'] is not None and frame['checksum'] != s._checksums.get(s._tick):
            raise ValueError('Recovery drain desync')
        from game.core.commands import PlayerCommand
        gm.state.command_queue.extend(PlayerCommand.from_dict(d) for d in frame['commands'])
        gm.step(FIXED_DT)
        s._frames.pop(s._tick, None)
        s._inputs.pop(s._tick, None)
        s._checksums.pop(s._tick, None)
        s._tick = gm.state.tick
        s._sealed = None
        self.trim()

    def build_bundle(self, gm):
        self.check()
        if any(r['tick'] != self.target for r in self.drained.values()):
            raise ValueError('Incomplete canonical drain')
        hashes = {r['checksum'] for r in self.drained.values()}
        if len(hashes) != 1:
            raise ValueError('Recovery canonical graph desync')
        b = self.target
        inputs = {}
        for slot, report in self.drained.items():
            self.validate_report(report, slot)
            batches = {x['tick']: x for x in report['batches']}
            for t in range(b, b+INPUT_DELAY):
                if t >= INPUT_DELAY and t not in batches:
                    raise ValueError('Recovery journal gap')
            if (report['sealed'] is not None
                    and (b+INPUT_DELAY not in batches or batches[b+INPUT_DELAY]['checksum'] != report['sealed'])):
                raise ValueError('Recovery sealed frontier mismatch')
            for t, accepted in self.s._inputs.items():
                if t >= b and slot in accepted:
                    batch = batches.get(t)
                    if batch is None or any(accepted[slot][k] != batch[k] for k in ('commands', 'checksum')):
                        raise ValueError('Conflicting accepted input retry')
            for t, batch in batches.items():
                if t >= b:
                    inputs.setdefault(t, {})[slot] = batch
        frames = []
        for t in range(b, b+INPUT_DELAY):
            if t < INPUT_DELAY and t != 0:
                frames.append(dict(type='frame', tick=t, commands=[], checksum=None))
                continue
            entries = inputs.get(t, {})
            if len(entries) != self.s._options['human_count'] or len({i['checksum'] for i in entries.values()}) != 1:
                raise ValueError('Recovery future input desync or gap')
            frames.append(dict(type='frame', tick=t, checksum=next(iter(entries.values()))['checksum'],
                               commands=[c for slot in sorted(entries) for c in entries[slot]['commands']]))
        graph = capture_snapshot(gm)
        self.check()
        # JSON snapshot nesting is retained, not an executable object codec.
        bundle = dict(epoch=self.epoch, tick=b, graph=json.loads(graph), frames=frames,
                      reports=[self.drained[slot] for slot in range(self.s._options['human_count'])])
        data = _json(bundle)
        if len(data) > MAX_SNAPSHOT:
            raise ValueError('Recovery bundle size limit')
        self.bundle_digest = hashlib.sha256(data).hexdigest()
        self.graph_digest = precise_checksum(gm)
        if self.pending_tokens is None:
            self.pending_tokens = {slot: secrets.token_hex(32) for slot in self.tokens}
        for peer in self.s._peers:
            if peer.slot is not None:
                # Install ACK proves the next credential reached its owner before
                # committing rotation, even when the later resume packet is lost.
                self.private(peer, pending=True)
                peer.send(dict(type='recovery_bundle', epoch=self.epoch, digest=self.bundle_digest,
                               graph=self.graph_digest, tick=b))
                self.senders[peer] = ChunkSender(data)
        self.install_bundle(data)

    def install_bundle(self, data):
        self.check()
        bundle = json.loads(data, object_pairs_hook=_unique_object)
        schema(bundle, 'epoch tick graph frames reports')
        if bundle['epoch'] != self.epoch or bundle['tick'] != self.target:
            raise ValueError('Recovery bundle identity mismatch')
        if type(bundle['reports']) is not list or len(bundle['reports']) != self.s._options['human_count']:
            raise ValueError('Recovery bundle humans mismatch')
        for slot, report in enumerate(bundle['reports']):
            schema(report, 'type epoch tick checksum batches pending sealed')
            self.validate_report(report, slot)
            if report['epoch'] != self.epoch or report['tick'] != self.target or report['checksum'] != self.graph_digest:
                raise ValueError('Recovery bundle report mismatch')
        if type(bundle['frames']) is not list or len(bundle['frames']) != INPUT_DELAY:
            raise ValueError('Recovery bundle frame count')
        journal = {}
        for slot, report in enumerate(bundle['reports']):
            batches = {entry['tick']: entry for entry in report['batches']}
            expected_targets = {t for t in range(self.target, self.target+INPUT_DELAY)
                                if t == 0 or t >= INPUT_DELAY}
            if report['sealed'] is not None:
                expected_targets.add(self.target+INPUT_DELAY)
            if set(batches) != expected_targets:
                raise ValueError('Recovery journal spent/gap/frontier mismatch')
            for t in range(self.target, self.target+INPUT_DELAY):
                if t >= INPUT_DELAY or t == 0:
                    if t not in batches:
                        raise ValueError('Recovery journal gap')
                    journal.setdefault(t, {})[slot] = batches[t]
            if report['sealed'] is not None:
                sealed = batches.get(self.target+INPUT_DELAY)
                if sealed is None or sealed['checksum'] != report['sealed']:
                    raise ValueError('Recovery journal sealed frontier mismatch')
        for t, frame in enumerate(bundle['frames'], self.target):
            self.validate_frame(frame)
            if frame['tick'] != t:
                raise ValueError('Recovery bundle frame sequence')
            entries = journal.get(t, {})
            expected_commands = [c for slot in sorted(entries) for c in entries[slot]['commands']]
            hashes = {entry['checksum'] for entry in entries.values()}
            expected_checksum = next(iter(hashes)) if hashes else None
            if (len(hashes) > 1 or frame['commands'] != expected_commands
                    or frame['checksum'] != expected_checksum):
                raise ValueError('Recovery frame disagrees with journal')
        manager = restore_snapshot(_json(bundle['graph']))
        self.check()
        if manager.state.tick != self.target or precise_checksum(manager) != self.graph_digest:
            raise ValueError('Recovery bundle graph mismatch')
        self.bundle = bundle
        self.manager = manager
        self.delivered = False
        self.phase = 'install'

    def take_manager(self):
        if self.s._status != 'recovering' or self.phase != 'install' or self.delivered:
            return None
        try:
            self.check()
        except ValueError as exc:
            self.s._fail(str(exc), phase='recovery')
            return None
        self.delivered = True
        return self.manager

    def acknowledge_install(self, manager):
        self.check()
        if (self.phase != 'install' or not self.delivered or manager is not self.manager
                or precise_checksum(manager) != self.graph_digest or self.s.local_player in self.acks):
            raise ValueError('Recovery install acknowledgement mismatch')
        self.check()
        self.acks.add(self.s.local_player)
        if self.s.is_host:
            self.finish()
        else:
            self.s._peers[0].send(dict(type='recovery_ack', epoch=self.epoch, tick=self.target,
                                     graph=self.graph_digest, bundle=self.bundle_digest))

    def finish(self):
        self.check()
        if len(self.acks) != self.s._options['human_count']:
            return
        self.generation += 1
        self.tokens = self.pending_tokens
        self.pending_tokens = None
        for peer in self.s._peers:
            if peer.slot is not None:
                self.private(peer)
        self.s._broadcast(dict(type='recovery_resume', epoch=self.epoch,
                               graph=self.graph_digest, bundle=self.bundle_digest))
        self.resume()
        for t in sorted(self.s._inputs):
            self.s._coordinate(t)

    def resume(self):
        self.check()
        s = self.s
        b = self.target
        reports = self.bundle['reports']
        local = reports[s.local_player]
        s._tick = b
        s._frames = {f['tick']: deepcopy(f) for f in self.bundle['frames']}
        s._pending = deepcopy(local['pending'])
        s._sealed = local['sealed']
        self.local = {x['tick']: deepcopy(x) for x in local['batches']}
        s._checksums = {t: x['checksum'] for t, x in self.local.items() if t >= b}
        s._inputs = {}
        if s.is_host:
            for slot, report in enumerate(reports):
                for batch in report['batches']:
                    if batch['tick'] >= b:
                        s._inputs.setdefault(batch['tick'], {})[slot] = deepcopy(batch)
            for peer in s._peers:
                if peer.slot is not None:
                    future = [x['tick'] for x in reports[peer.slot]['batches'] if x['tick'] >= b]
                    peer.next_tick = max(future, default=b+INPUT_DELAY-1)+1
            for frame in self.bundle['frames']:
                self.released(frame)
        else:
            s._peers[0].next_tick = b+INPUT_DELAY
        s._status = 'running'
        s._progress = time.monotonic()
        s._loading_started = None
        self.deadline = None
        self.phase = 'running'
        self.senders = {}
        self.manager = None
        self.trim()
