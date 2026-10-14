#!/usr/bin/env python3
"""Real TCP production recovery diagnostic; no renderer and no mock transport.

All 2/3/4 humans and paid pending/lost-before-accept/accepted-unspent/spent
batches, intentional skew, public pause/drain/install API, exact future hashes.
Trusted unencrypted localhost only. Output NEVER includes bearer credentials.
This is a tight-loop recovery probe, not a real-time throughput benchmark.
"""
import argparse
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import socket
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from game.core.commands import BuildStationCommand
from game.core.manager import GameManager
from game.core.vectors import Vec3
from game.net.lan import LanSession, default_lan_options, FIXED_DT, precise_checksum
from game.net.reconnect import capture_snapshot, restore_snapshot


def pump(sessions, predicate, seconds=8):
    until = time.monotonic()+seconds
    while time.monotonic() < until:
        for session in sessions:
            session.poll()
            if session.snapshot['status'] == 'error':
                raise RuntimeError(session.snapshot['error'])
        if predicate():
            return
        time.sleep(.001)
    raise RuntimeError('Diagnostic bounded wait expired')


def align(sessions, managers, target):
    until = time.monotonic()+8
    while any(m.state.tick < target for m in managers) and time.monotonic() < until:
        for session, manager in zip(sessions, managers):
            if manager.state.tick < target:
                session.advance(manager, FIXED_DT)
            else:
                session.poll()
            if session.snapshot['status'] == 'error':
                raise RuntimeError(session.snapshot['error'])
    if any(m.state.tick != target for m in managers):
        raise RuntimeError('Diagnostic lockstep failed to reach target')
    if len({precise_checksum(m) for m in managers}) != 1:
        raise RuntimeError('Diagnostic exact graph mismatch')


def run_case(humans, mode, end_tick):
    with socket.socket() as probe:
        probe.bind(('127.0.0.1', 0))
        port = probe.getsockname()[1]
    options = default_lan_options()
    options.update(human_count=humans, ai_count=min(1, 4-humans), map_id='skirmish04')
    sessions = []
    try:
        host = LanSession.host(port, options, recovery=True)
        sessions.append(host)
        for _ in range(humans-1):
            sessions.append(LanSession.join('127.0.0.1', port, recovery=True))
        pump(sessions, lambda: all(len(s.snapshot['players']) == humans for s in sessions))
        for session in sessions:
            session.set_ready(True)
        pump(sessions, lambda: host.snapshot['can_start'])
        host.start()
        pump(sessions, lambda: all(s.launch for s in sessions))
        managers = [GameManager.start_skirmish(s.launch['map_def']) for s in sessions]
        for s, m in zip(sessions, managers):
            m.state._net_session = s
        align(sessions, managers, 8)
        control = restore_snapshot(capture_snapshot(managers[0]))
        commands = []
        for slot, gm in enumerate(managers):
            builder = next(e for e in gm.state.entities.values() if e.owner == slot and e.is_construction
                           and 'research_station' in gm.ds.ships[e.data_id].can_build_stations)
            command = BuildStationCommand(slot, builder.id, 'research_station', builder.pos+Vec3(600, 0, 0))
            commands.append(command)
            gm.state.queue_command(command)
        lost = sessions[1]
        if mode == 'lost_before_accept':
            # Inject only write backpressure on the REAL connected TCP socket;
            # production advance still seals its actual pending human batches.
            class BlockWrites:
                def __init__(self, sock):
                    self.sock = sock
                def __getattr__(self, name):
                    return getattr(self.sock, name)
                def send(self, data):
                    raise BlockingIOError('Intentional diagnostic write backpressure')
            peer = lost._peers[0]
            original_socket = peer.sock
            peer.sock = BlockWrites(original_socket)
            lost.advance(managers[1], FIXED_DT)
            if 1 in host._inputs.get(11, {}):
                raise RuntimeError('Lost-before-accept case was already accepted')
        elif mode == 'accepted_unspent':
            lost.advance(managers[1], FIXED_DT)
            pump(sessions, lambda: 1 in host._inputs.get(11, {}))
        elif mode == 'spent':
            align(sessions, managers, 12)
        start = max(m.state.tick for m in managers)
        until = time.monotonic()+3
        while managers[0].state.tick < start+2 and time.monotonic() < until:
            host.advance(managers[0], FIXED_DT)
            for session in sessions[1:]:
                session.poll()
        old_ticks = [m.state.tick for m in managers]
        if max(old_ticks) == min(old_ticks):
            raise RuntimeError('Diagnostic failed to produce actual graph skew')
        continuing = {p.slot: p for p in host._peers if p.slot != 1}
        if mode == 'lost_before_accept' and 1 in host._inputs.get(11, {}):
            raise RuntimeError('Diagnostic backpressure leaked input before interruption')
        lost._peers[0].sock.shutdown(socket.SHUT_RDWR)
        if mode == 'lost_before_accept':
            lost._peers[0].sock = original_socket
        installed = set()
        drain_calls = [0]*humans
        drain_steps = [0]*humans
        until = time.monotonic()+8
        recovery_started = time.monotonic()
        while time.monotonic() < until:
            for index, (session, manager) in enumerate(zip(sessions, managers)):
                session.poll()
                if session.snapshot['status'] == 'error':
                    raise RuntimeError(session.snapshot['error'])
                if session.snapshot['status'] == 'recovering':
                    before = manager.state.tick
                    if session.advance(manager, 600.) or manager.state.tick != before:
                        raise RuntimeError('Ordinary advance executed during recovery')
                    drain_calls[index] += 1
                    session.recovery_step(manager)
                    delta = manager.state.tick-before
                    if delta not in (0, 1):
                        raise RuntimeError('Recovery accumulated catch-up debt')
                    drain_steps[index] += delta
                    candidate = session.take_restored_manager()
                    if candidate is not None:
                        managers[index] = candidate
                        candidate.state._net_session = session
                        session.acknowledge_install(candidate)
                        installed.add(index)
            if len(installed) == humans and all(s.snapshot['status'] == 'running' for s in sessions):
                break
        else:
            raise RuntimeError('Diagnostic recovery timed out')
        recovery_ms = (time.monotonic()-recovery_started)*1000
        for slot, peer in continuing.items():
            if next(p for p in host._peers if p.slot == slot) is not peer:
                raise RuntimeError('Continuing socket was replaced')
        if host._listener is None:
            raise RuntimeError('Original listener was destroyed')
        trace = []
        barrier = managers[0].state.tick
        for tick in range(barrier, end_tick+1):
            while control.state.tick < tick:
                if control.state.tick == 11:
                    control.state.command_queue.extend(commands)
                control.step(FIXED_DT)
            align(sessions, managers, tick)
            hashes = [precise_checksum(m) for m in managers]
            reference = precise_checksum(control)
            if any(h != reference for h in hashes):
                raise RuntimeError(f'Future control mismatch at tick {tick}')
            trace.append(dict(tick=tick, hashes=hashes, control=reference))
        queues = [[len(m.state.entities[c.unit_ids[0]].build_queue) for c in commands] for m in managers]
        if any(n != 1 for queue in queues for n in queue):
            raise RuntimeError('Paid batch duplicated or dropped')
        return dict(humans=humans, case=mode, old_ticks=old_ticks, canonical_tick=barrier,
                    drain_calls=drain_calls, drain_steps=drain_steps, recovery_ms=recovery_ms,
                    paid_queue_counts=queues, retained_slots=sorted(continuing),
                    listener_retained=True, frame_history_counts=[len(s._recovery.history) for s in sessions],
                    journal_counts=[len(s._recovery.local) for s in sessions], future_trace=trace)
    finally:
        for session in sessions:
            session.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--ticks', type=int, default=60)
    parser.add_argument('--humans', type=int, choices=(2, 3, 4))
    parser.add_argument('--scenario', choices=('pending', 'lost_before_accept', 'accepted_unspent', 'spent'))
    args = parser.parse_args()
    if not 20 <= args.ticks <= 600:
        parser.error('--ticks must be 20..600')
    cases = [args.scenario] if args.scenario else ['pending', 'lost_before_accept', 'accepted_unspent', 'spent']
    humans = [args.humans] if args.humans else [2, 3, 4]
    args.out.mkdir(parents=True, exist_ok=True)
    collected = []
    for count in humans:
        for case in cases:
            result = run_case(count, case, args.ticks)
            collected.append(result)
            (args.out/f'{count}-{case}.json').write_text(json.dumps(result, indent=2)+'\n')
            print(f'{count} humans / {case}: exact future ticks {len(result["future_trace"])}; paid once; recovery {result["recovery_ms"]:.1f} ms')
    if len(collected) != len(humans)*len(cases):
        raise RuntimeError('Diagnostic scenario count mismatch')
    summary = dict(passed=True, scenario_count=len(collected), cases=collected,
                   evidence='Real localhost TCP and real production managers; tight-loop diagnostic, not FPS benchmark',
                   source_sha256={name: hashlib.sha256((ROOT/name).read_bytes()).hexdigest()
                                  for name in ('game/net/lan.py', 'game/net/live_recovery.py', 'game/net/reconnect.py')})
    (args.out/'summary.json').write_text(json.dumps(summary, indent=2)+'\n')
    print(f'PASS: {len(collected)} real TCP cases, output {args.out}')


if __name__ == '__main__':
    main()
